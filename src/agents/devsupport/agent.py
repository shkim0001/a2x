"""개발 지원 Agent (T3-5): 자산 상세로 연계 예시 코드를 만든다.

코드는 템플릿을 코드로 채운다(LLM이 코드를 쓰지 않음). 비밀 값은 <YOUR_TOKEN> 같은 자리표시만 쓰고,
구독 ID · Tool 이름 · 엔드포인트는 사용자의 실제 권한(승인된 구독)에서 채운다.
LLM이 있으면 질문에 맞춘 짧은 설명만 덧붙인다."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from anyio import to_thread

from src.agents.devsupport.prompts import SYSTEM
from src.agents.devsupport.templates import _headers, api_curl, api_python, mcp_curl, mcp_python, portal_curl
from src.agents.state import AgentResult, UserCtx
from src.knowledge.evidence import keywords
from src.shared import trace
from src.shared.llm import LLMClient, LLMUnavailable, note_skipped


NOISE = {"코드", "예시", "샘플", "예제", "python", "파이썬", "curl", "호출", "연동", "클라이언트", "설정", "만들어", "보여", "작성", "api", "mcp", "서버", "tool", "포탈", "jsonrpc", "json", "rpc", "http"}


class Portal(Protocol):
    def search_catalog(self, q: str | None = None, live_only: bool = True) -> list[dict[str, Any]]: ...
    def get_asset_detail(self, asset_id: int) -> dict[str, Any] | None: ...
    def list_my_access(self, asset_id: int | None = None) -> list[dict[str, Any]]: ...


def explicit_langs(message: str) -> list[str]:
    t = message.lower()
    return [lang for lang, pat in (("python", r"python|파이썬"), ("curl", r"curl|json-?rpc|http\s?호출"), ("portal", r"포탈\s?api|포탈\s?연동|권한\s?확인")) if re.search(pat, t)]


def _pick(items: list[dict], message: str, key: str) -> dict | None:
    t = message.lower()
    named = sorted((it for it in items if it[key].lower() in t), key=lambda it: len(it[key]), reverse=True)  # 가장 길게 일치한 것
    if named:
        return named[0]
    return next((it for it in items if it.get("kind", "READ") == "READ" or it.get("method") == "GET"), items[0] if items else None)


def _find_asset(message: str, portal: Portal, asset_id: int | None) -> tuple[dict | None, list[dict]]:
    """메시지가 자산을 하나로 특정하면 그것(화면에서 고른 자산보다 우선), 아니면 화면 문맥의 자산."""
    named, cands = _match_asset(message, portal)
    if named is not None:
        return named, []
    if asset_id:
        return portal.get_asset_detail(asset_id), []
    return None, cands


def _match_asset(message: str, portal: Portal) -> tuple[dict | None, list[dict]]:
    terms = [w for w in keywords(message) if w not in NOISE]
    t = message.lower()
    want = "MCP" if "mcp" in t and "api" not in t else "API" if "api" in t and "mcp" not in t else None
    if terms:
        # 이름 일치 단어 수 + 메시지가 말한 종류(MCP · API)면 0.5점
        scored = [(sum(w in f"{a['name']} {a['system_code']} {a['system_name']}".lower() for w in terms) + (0.5 if a["type"] == want else 0), a) for a in portal.search_catalog(None)]
        top = max((sc for sc, _ in scored), default=0)
        cands = [a for sc, a in scored if sc == top and top >= 1]
        if len(cands) == 1:
            return portal.get_asset_detail(cands[0]["id"]), []
        if cands:
            return None, cands
    return None, []


async def run(message: str, portal: Portal, user: UserCtx, llm: LLMClient | None = None, asset_id: int | None = None) -> AgentResult:
    asset, cands = _find_asset(message, portal, asset_id)
    langs = explicit_langs(message) or (["python", "curl"] if asset else [])
    tools_used = ["portal.search_catalog" if not asset_id else "portal.get_asset_detail"]

    if asset is None and (cands or "portal" not in langs):
        mine = portal.list_my_access()
        tools_used.append("portal.list_my_access")
        options = cands or [{"system_code": m["client_system_code"], "name": m["asset_name"]} for m in mine]
        return AgentResult(
            answer=("후보가 여럿입니다. " if cands else "") + "어떤 API · MCP의 연계 코드가 필요하신가요? 카탈로그에서 항목을 고르거나 이름을 알려 주세요.",
            actions=[{"type": "ask", "label": o["name"], "message": f"{o['name']} 호출 코드 예시"} for o in options[:6]] or [{"type": "open", "page": "catalog", "label": "카탈로그 열기"}],
            used_tools=tools_used,
        )

    access = portal.list_my_access(asset["id"]) if asset else portal.list_my_access()
    tools_used.append("portal.list_my_access")
    sub = access[0] if access else None
    sub_id = sub["subscription_id"] if sub else None
    notes: list[str] = []
    blocks: list[tuple[str, str, str]] = []  # (제목, 언어, 코드)

    tool = None
    if asset and asset["type"] == "MCP":
        tool = _pick(asset["tools"], message, "name")
        headers = _headers(asset, user.email, sub_id)
        if "python" in langs:
            blocks.append(("Python (공식 mcp SDK)", "python", mcp_python(asset, tool, headers)))
        if "curl" in langs:
            blocks.append(("curl (JSON-RPC tools/call)", "bash", mcp_curl(asset, tool, headers)))
        if asset["source"] == "MCP_CONVERTED":
            if sub is None:
                notes.append("아직 이 MCP의 승인된 시스템 구독이 없어 <SUBSCRIPTION_ID>로 두었습니다. 카탈로그에서 구독 신청 → 승인 후 Tool을 신청하세요.")
            elif tool and tool["name"] not in sub["my_tools"]:
                notes.append(f"구독 #{sub_id}({sub['client_system_code']})에서 '{tool['name']}' Tool 권한이 아직 없습니다. 내 권한 화면에서 Tool을 신청하세요(없으면 403).")
        else:
            notes.append(f"타겟 시스템이 직접 운영하는 MCP 서버입니다. 인증({asset['auth_type'] or '시스템 담당자에게 확인'}) 토큰을 <YOUR_TOKEN>에 넣으세요.")
        if tool and not tool.get("input_schema"):
            notes.append("입력 인자는 tools/list 응답의 inputSchema를 확인해 채우세요.")
    elif asset:
        op = _pick(asset["operations"], message, "path")
        headers = {"Authorization": "Bearer <YOUR_TOKEN>"}
        if "curl" in langs:
            blocks.append(("curl", "bash", api_curl(asset, op, headers)))
        if "python" in langs:
            blocks.append(("Python (httpx)", "python", api_python(asset, op, headers)))
        notes.append(
            "API 연계는 시스템 구독 단위입니다. " + (f"승인된 구독 #{sub_id}({sub['client_system_code']})이 있습니다. " if sub else "먼저 카탈로그에서 시스템 구독을 신청하세요. ")
            + f"인증({asset['auth_type'] or '방식은 시스템 담당자에게 확인'}) 정보는 프로바이더 시스템 담당자에게 받으세요."
        )
    if "portal" in langs:
        blocks.append(("포탈 API (curl)", "bash", portal_curl(user.email, sub_id, tool["name"] if tool else None)))

    head = f"'{asset['name']}'({asset['system_code']} · {'변환 MCP' if asset['source'] == 'MCP_CONVERTED' else asset['type']}) 호출 예시입니다." if asset else "포탈 API 호출 예시입니다."
    explanation, used_llm = "", None
    trace.step(trace.actor(), "예시 코드 채우기(템플릿)", ", ".join(b[0] for b in blocks) or "없음")
    if llm is None or not llm.available:
        note_skipped("API 키 없음 → 설명 문장 없이 코드만")
    if llm is not None and llm.available:
        info = json.dumps({k: asset[k] for k in ("name", "type", "source", "endpoint", "base_url", "auth_type")} if asset else {}, ensure_ascii=False)
        try:
            content = f"[자산]\n{info}\n[예시 코드 종류]\n{', '.join(b[0] for b in blocks)}\n[참고]\n{' '.join(notes)}\n\n[질문]\n{message}"
            # LLM 호출은 동기 작업이라 스레드에서 실행한다(서버 이벤트 루프를 막지 않음)
            r = await to_thread.run_sync(lambda: llm.complete([{"role": "user", "content": content}], system=SYSTEM, max_tokens=600, effort="low"))
            explanation, used_llm = r.text.strip(), r.model
        except LLMUnavailable:
            pass

    parts = [head] + ([explanation] if explanation else [])
    parts += [f"**{title}**\n```{lang}\n{code.rstrip()}\n```" for title, lang, code in blocks]
    parts += [f"※ {n}" for n in notes]
    parts.append("비밀 값(<YOUR_TOKEN> 등)은 코드에 직접 넣지 말고 환경변수로 관리하세요.")
    source = [{"type": "asset", "id": asset["id"], "label": f"카탈로그 › {asset['system_code']} {asset['name']}"}] if asset else []
    return AgentResult(answer="\n\n".join(parts), sources=source, used_tools=tools_used, used_llm=used_llm)
