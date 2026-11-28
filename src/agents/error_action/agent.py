"""오류 조치 Agent (T3-6): 호출 실패를 규칙으로 분류하고 원인 · 조치를 안내한다.

두 가지 모드(모두 코드 판정):
1) 트랜잭션 진단: 화면에서 고른 트랜잭션(또는 메시지의 TX ID) 한 건. 응답 코드 → 원인 범주(src/monitoring/service.py RULES),
   실패 단계, 그리고 DB 사실 확인(403이면 Tool 신청 상태, 429면 같은 연계 반복 수, 5xx면 같은 시각 다른 연계 실패 수).
2) 기간 요약: 조회 범위(화면과 같은 규칙) 안의 실패를 (프로바이더, 응답 코드)로 묶어 건수 · 시간대 집중 · 같은 연계 반복 ·
   영향받은 클라이언트 수를 계산한다.
LLM은(있으면) 계산 결과를 짧게 요약하는 문장에만 쓴다. 담당자 연락처 같은 식별 값은 LLM에 보내지 않는다."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from anyio import to_thread

from src.agents.error_action.prompts import SYSTEM
from src.agents.state import AgentResult
from src.monitoring.service import classify
from src.shared import trace
from src.shared.llm import LLMClient, LLMUnavailable, note_skipped


KST = timezone(timedelta(hours=9))


TX_RE = re.compile(r"\b((?:TX|MCP|CV)-[A-Za-z0-9-]+)\b")


SLOW_MS = 3000


STATUS_TEXT = {
    None: ("Tool 신청 내역이 없습니다.", "내 권한 화면에서 이 Tool을 신청하세요."),
    "PENDING": ("Tool 신청이 승인 대기 중입니다.", "프로바이더 시스템 담당자의 승인이 필요합니다."),
    "REJECTED": ("Tool 신청이 반려됐습니다.", "반려 사유를 확인하고 다시 신청하세요."),
    "CANCELLED": ("Tool 권한이 해지됐습니다.", "필요하면 다시 신청하세요."),
    "APPROVED": ("지금은 Tool 권한이 승인돼 있습니다(호출 당시에는 없었을 수 있음).", "다시 호출해 보세요."),
}


class Portal(Protocol):
    def list_systems(self) -> list[dict[str, Any]]: ...
    def get_call_log(self, tx_id: str) -> dict[str, Any] | None: ...
    def query_call_logs(self, **filters: Any) -> list[dict[str, Any]]: ...
    def tool_request_status(self, user_id: int, subscription_id: int, tool_id: int) -> str | None: ...
    def system_contacts(self, system_id: int) -> list[str]: ...


def _kst(dt: datetime) -> datetime:
    return dt.astimezone(KST)


def _t(dt: datetime) -> str:
    return _kst(dt).strftime("%m/%d %H:%M")


def parse_period(message: str, now: datetime) -> tuple[datetime, datetime, str]:
    """메시지의 기간 표현 → (시작, 끝, 표시). 기본은 최근 24시간."""
    t = message.replace(" ", "")
    today = _kst(now).replace(hour=0, minute=0, second=0, microsecond=0)
    if "그제" in t or "그저께" in t or "이틀전" in t:
        return today - timedelta(days=2), today - timedelta(days=1), "그제"
    if "어제" in t:
        return today - timedelta(days=1), today, "어제"
    if "오늘" in t:
        return today, now, "오늘"
    if "이번주" in t:
        return today - timedelta(days=today.weekday()), now, "이번 주"
    if m := re.search(r"(?:최근|지난)?(\d+)일", t):
        return now - timedelta(days=int(m.group(1))), now, f"최근 {m.group(1)}일"
    if m := re.search(r"(?:최근|지난)?(\d+)시간", t):
        return now - timedelta(hours=int(m.group(1))), now, f"최근 {m.group(1)}시간"
    return now - timedelta(hours=24), now, "최근 24시간"


def parse_filters(message: str, systems: list[dict[str, Any]]) -> dict[str, Any]:
    t = message.lower()
    out: dict[str, Any] = {}
    if codes := set(re.findall(r"(?<!\d)([45]\d\d)(?!\d)", message)):
        out["codes"] = codes
    if "mcp" in t and "api" not in t:
        out["kind"] = "MCP"
    elif "api" in t and "mcp" not in t:
        out["kind"] = "API"
    named = {s["id"] for s in systems if re.search(rf"(?<![a-z0-9]){re.escape(s['code'].lower())}(?![a-z0-9])", t) or s["name"].lower() in t}
    if named:
        out["system_ids"] = named
    return out


def _failed_stage(log: dict) -> str | None:
    return next((s["name"] for s in log["stages"] if not s.get("ok", True)), None)


def diagnose(log: dict, portal: Portal) -> tuple[list[str], list[str], dict[str, Any]]:
    """한 건 진단 → (사실 줄, 조치 줄, LLM용 요약 사실)."""
    ec = classify(log["code"])
    facts = [f"{_t(log['started_at'])} {log['client']} → {log['provider']} · {log['name']} · 응답 {log['code']} · {log['duration_ms']}ms"]
    if ec is None:
        facts.append("성공한 호출입니다." + (f" 다만 응답이 {log['duration_ms']}ms로 느립니다." if log["duration_ms"] >= SLOW_MS else ""))
        return facts, [], {"code": log["code"], "success": True}
    facts.append(f"원인 범주: **{ec.category}**" + (f" (실패 단계: {st})" if (st := _failed_stage(log)) else ""))
    if log["error_message"]:
        facts.append(f"오류 메시지: {log['error_message']}")
    actions = [ec.action]
    extra: dict[str, Any] = {"code": log["code"], "category": ec.category}
    code = int(log["code"]) if log["code"].isdigit() else 500
    t0 = log["started_at"]

    if code == 403 and log["kind"] == "MCP" and log["tool_id"] and log["user_id"] and log["subscription_id"]:
        status = portal.tool_request_status(log["user_id"], log["subscription_id"], log["tool_id"])
        fact, act = STATUS_TEXT.get(status, STATUS_TEXT[None])
        facts.append(fact)
        actions = [act]
        extra["tool_request"] = status or "없음"
    elif code == 429 and log["subscription_id"]:
        same = portal.query_call_logs(since=t0 - timedelta(hours=1), until=t0 + timedelta(hours=1), codes={"429"}, subscription_id=log["subscription_id"], limit=None)
        facts.append(f"같은 연계(구독 #{log['subscription_id']})에서 앞뒤 1시간 동안 429가 {len(same)}건 있습니다.")
        extra["same_429"] = len(same)
    elif code == 401 and log["subscription_id"]:
        same = portal.query_call_logs(since=t0 - timedelta(hours=24), until=t0 + timedelta(minutes=1), codes={"401"}, subscription_id=log["subscription_id"], limit=None)
        if len(same) > 1:
            facts.append(f"같은 연계에서 최근 24시간 401이 {len(same)}건입니다. 토큰이 만료된 뒤 계속 실패하고 있을 수 있습니다.")
        extra["same_401"] = len(same)
    elif code >= 500 and log["provider_system_id"]:
        near = [x for x in portal.query_call_logs(since=t0 - timedelta(minutes=30), until=t0 + timedelta(minutes=30), failed_only=True, system_ids={log["provider_system_id"]}, limit=None)
                if x["provider_system_id"] == log["provider_system_id"] and int(x["code"] or 0) >= 500]
        clients = {x["client_system_id"] for x in near}
        if len(near) >= 3 and len(clients) >= 2:
            facts.append(f"같은 시각(±30분) {log['provider']}에서 5xx 실패가 {len(near)}건, 클라이언트 {len(clients)}곳에서 함께 났습니다. 대상 시스템 장애일 가능성이 높습니다.")
        else:
            facts.append(f"같은 시각(±30분) {log['provider']}의 다른 5xx 실패는 {max(len(near) - 1, 0)}건입니다. 일시적 오류일 수 있으니 재시도 후에도 반복되면 문의하세요.")
        extra.update(near_5xx=len(near), clients=len(clients))
    if ec.side == "PROVIDER" or code == 429:
        if contacts := portal.system_contacts(log["provider_system_id"]):
            actions.append(f"대상 시스템 담당자: {', '.join(contacts)}")
    return facts, actions, extra


def summarize(logs: list[dict], total: int, portal: Portal) -> tuple[list[str], dict[str, Any]]:
    """기간 실패 요약 → (보고 줄, LLM용 요약 사실)."""
    groups: dict[tuple, list[dict]] = {}
    for lg in logs:
        groups.setdefault((lg["provider_system_id"], lg["provider"], lg["code"]), []).append(lg)
    lines, facts = [], []
    for (pid, provider, code), items in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:3]:
        ec = classify(code)
        notes = []
        hours = Counter(_kst(x["started_at"]).strftime("%m/%d %H시대") for x in items)
        hour, hn = hours.most_common(1)[0]
        if hn >= 5 and hn >= len(items) * 0.5:
            notes.append(f"{hour}에 {hn}건 집중")
        subs = Counter(x["subscription_id"] for x in items if x["subscription_id"])
        if subs:
            sid, sn = subs.most_common(1)[0]
            if sn >= 5 and sn >= len(items) * 0.6:
                client = next(x["client"] for x in items if x["subscription_id"] == sid)
                notes.append(f"같은 연계(구독 #{sid}, {client})에서 {sn}건 반복")
        clients = {x["client_system_id"] for x in items}
        if ec and ec.side == "PROVIDER" and len(clients) >= 2:
            notes.append(f"클라이언트 {len(clients)}곳이 함께 실패 → 대상 시스템 문제 가능성")
        head = f"**{provider} · {code} {ec.category if ec else ''}** — {len(items)}건" + (f" ({'; '.join(notes)})" if notes else "")
        act = ec.action if ec else ""
        if ec and (ec.side == "PROVIDER" or code == "429") and (contacts := portal.system_contacts(pid)):
            act += f" 담당자: {', '.join(contacts)}"
        lines.append(f"- {head}\n  - 조치: {act}\n  - 예: {items[0]['tx_id']} ({_t(items[0]['started_at'])})")
        facts.append({"provider": provider, "code": code, "category": ec.category if ec else "", "count": len(items), "notes": notes})
    rest = len(groups) - 3
    if rest > 0:
        lines.append(f"- 그 밖에 {rest}개 묶음, {sum(len(v) for v in list(sorted(groups.values(), key=len, reverse=True))[3:])}건")
    return lines, {"failed": len(logs), "total": total, "top": facts}


def _llm_summary(llm: LLMClient | None, message: str, data: dict) -> tuple[str, str | None]:
    if llm is None or not llm.available:
        note_skipped("API 키 없음 → 요약 문장 없이 규칙 결과만")
        return "", None
    try:
        r = llm.complete([{"role": "user", "content": f"[분석 결과]\n{json.dumps(data, ensure_ascii=False, default=str)}\n\n[질문]\n{message}"}], system=SYSTEM, max_tokens=300, effort="low")
        return r.text.strip(), r.model
    except LLMUnavailable:
        return "", None


async def run(message: str, portal: Portal, llm: LLMClient | None = None, transaction_id: str | None = None, page: str | None = None, now: datetime | None = None) -> AgentResult:
    now = now or datetime.now(timezone.utc)
    tx = transaction_id or (m.group(1) if (m := TX_RE.search(message)) else None)

    if tx:
        log = portal.get_call_log(tx)
        if log is None:
            return AgentResult(answer=f"트랜잭션 {tx}를 찾을 수 없거나 조회 권한이 없습니다.", used_tools=["portal.get_call_log"])
        facts, actions, data = diagnose(log, portal)
        trace.step(trace.actor(), "오류 분류 · 사실 확인(코드)", f"응답 {log['code']} → {data.get('category', '성공')}" + (f" · Tool 신청 {data['tool_request']}" if "tool_request" in data else ""), ok=log["success"] or bool(actions))
        summary, used_llm = await to_thread.run_sync(lambda: _llm_summary(llm, message, data)) if actions else ("", None)
        parts = [f"트랜잭션 {tx} 진단 결과입니다."] + ([summary] if summary else []) + ["\n".join(f"- {f}" for f in facts)]
        if actions:
            parts.append("**조치**\n" + "\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1)))
        nav = [{"type": "open", "page": "usage-mcp" if log["kind"] == "MCP" else "usage-api", "label": "사용내역에서 보기", "tx_id": tx}]
        if log["code"] == "403" and log["kind"] == "MCP":
            nav.append({"type": "request", "asset_id": str(log["asset_id"]), "label": "Tool 사용 신청"} if log.get("asset_id")
                       else {"type": "open", "page": "catalog", "label": "카탈로그에서 Tool 신청"})
        return AgentResult(answer="\n\n".join(parts), sources=[{"type": "call_log", "tx_id": tx}], actions=nav,
                           used_tools=["portal.get_call_log", "portal.query_call_logs"], used_llm=used_llm)

    since, until, label = parse_period(message, now)
    filters = parse_filters(message, portal.list_systems())
    all_logs = portal.query_call_logs(since=since, until=until, limit=None, **{k: v for k, v in filters.items() if k != "codes"})
    failed = [x for x in all_logs if not x["success"] and (not filters.get("codes") or x["code"] in filters["codes"])]
    scope = label + (f" · 응답 {', '.join(sorted(filters['codes']))}" if filters.get("codes") else "") + (f" · {filters['kind']}" if filters.get("kind") else "")
    tools = ["portal.list_systems", "portal.query_call_logs"]
    if not failed:
        return AgentResult(answer=f"{scope} 동안 조회 범위 안에서 실패한 호출이 없습니다(전체 {len(all_logs)}건).", used_tools=tools)
    lines, data = summarize(failed, len(all_logs), portal)
    trace.step(trace.actor(), "실패 묶음 분석(코드)", f"{scope}: {len(all_logs)}건 중 실패 {len(failed)}건 → " + ", ".join(f"{t['code']}×{t['count']}" for t in data["top"]))
    summary, used_llm = await to_thread.run_sync(lambda: _llm_summary(llm, message, data))  # LLM 호출은 스레드에서
    rate = len(failed) / len(all_logs) * 100 if all_logs else 100.0
    parts = [f"{scope} 동안 호출 {len(all_logs)}건 중 {len(failed)}건 실패({rate:.1f}%)했습니다. 많은 순서로 묶었습니다."]
    parts += ([summary] if summary else []) + ["\n".join(lines)]
    parts.append("특정 건을 자세히 보려면 트랜잭션 ID(예: TX-…)를 알려 주세요.")
    page_key = "usage-mcp" if filters.get("kind") == "MCP" else "usage-api"
    return AgentResult(answer="\n\n".join(parts), sources=[{"type": "call_logs", "period": label, "failed": len(failed)}],
                       actions=[{"type": "open", "page": page_key, "label": "사용내역 열기"}], used_tools=tools, used_llm=used_llm)
