"""모니터링 샘플 호출 로그 생성기 (T1-2). 1차는 이 데이터로 모니터링 · 오류 조치 Agent를 만들고,
3차 Gateway 연동 시 실제 호출 로그로 바뀐다(같은 call_logs 테이블).

규칙(포탈 데이터와 맞춤):
- API 호출: 승인된 시스템 구독(API)의 클라이언트 시스템이 호출한다(사용자 없음).
- MCP 호출: 승인된 Tool 권한을 가진 사용자가 호출한다. 승인되지 않은 Tool 신청(대기 · 반려)은 가끔 403으로 거부된다.
- 평일이 주말보다 많고, 업무 시간에 몰리며, MCP 호출은 점점 늘어난다.
- 오류 조치 Agent 시연용 사건: 이틀 전 오전 한 프로바이더의 504 집중, 어제 한 연계의 429 반복.
- 같은 seed · now면 같은 데이터(재현 가능). 인증 값은 가린 형태로만 저장한다.

실행(루트에서): .venv\\Scripts\\python.exe -m src.monitoring.generator [--days 60] [--reset]
"""

from __future__ import annotations

import argparse

import random

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from src.catalog.models import Asset, AssetType, McpTool
from src.monitoring.models import CallKind, CallLog
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest
from src.systems.models import System

KST = timezone(timedelta(hours=9))
PREFIXES = ("TX-", "MCP-")  # 생성기가 만든 로그(컨버터 실제 호출 CV-는 지우지 않음)
GW = "https://a2x-gw.internal.example"

ERROR_TEXT = {
    400: "요청 형식 오류: 필수 필드 누락",
    401: "인증 실패: 토큰 만료",
    403: "권한 없음",
    404: "리소스 없음",
    429: "호출 한도 초과",
    500: "대상 시스템 내부 오류",
    502: "대상 시스템 연결 실패",
    504: "대상 시스템 응답 시간 초과",
}
# 평시 API 응답 코드 분포
API_CODES = [(200, 970), (400, 4), (401, 6), (404, 4), (429, 6), (500, 5), (504, 5)]  # 평시 실패 약 3%
# 시간대별 가중치(0~23시, KST): 업무 시간에 몰림
HOUR_WEIGHT = [1, 1, 1, 1, 1, 2, 4, 8, 14, 18, 18, 15, 10, 15, 18, 17, 15, 12, 8, 5, 4, 3, 2, 1]


@dataclass
class _Api:
    sub: SystemSubscription
    asset: Asset
    client: System


@dataclass
class _Mcp:
    sub: SystemSubscription
    asset: Asset
    tool: McpTool
    user_id: int
    user_email: str
    approved: bool
    status: str


def _ip(system: System) -> str:
    return system.servers[0].ip if system.servers else "10.0.0.1"


def _fill(path: str, r: random.Random) -> str:
    def val(m: re.Match) -> str:
        p = m.group(1)
        if re.search("order", p, re.I):
            return f"ORD-{r.randint(1000, 9999)}"
        if re.search("customer", p, re.I):
            return f"C{r.randint(100000, 999999)}"
        return f"{p.upper()}-{r.randint(1, 999)}"
    return re.sub(r"\{(\w+)\}", val, path)


def _stages(defs: list[tuple[str, int, bool]]) -> list[dict]:
    out = []
    for name, ms, ok in defs:
        out.append({"name": name, "ms": ms, "ok": ok})
        if not ok:  # 실패한 단계 뒤는 실행되지 않는다
            break
    return out


def _pick_time(day: datetime, r: random.Random) -> datetime:
    hour = r.choices(range(24), weights=HOUR_WEIGHT)[0]
    return day.replace(hour=hour, minute=r.randint(0, 59), second=r.randint(0, 59), microsecond=r.randint(0, 999) * 1000)


def _load(db: Session) -> tuple[list[_Api], list[_Mcp]]:
    subs = db.query(SystemSubscription).filter(SystemSubscription.status == RequestStatus.APPROVED).order_by(SystemSubscription.id).all()
    apis = [_Api(s, s.asset, s.client_system) for s in subs if s.asset.type == AssetType.API and s.asset.operations]
    mcps = []
    for tr in db.query(ToolRequest).order_by(ToolRequest.id).all():
        if tr.subscription.status != RequestStatus.APPROVED or tr.status == RequestStatus.CANCELLED:
            continue
        mcps.append(_Mcp(tr.subscription, tr.subscription.asset, tr.tool, tr.user_id, tr.user.email, tr.status == RequestStatus.APPROVED, tr.status.value))
    return apis, mcps


def _api_log(c: _Api, start: datetime, code: int, r: random.Random, seq: int) -> CallLog:
    op = r.choice(c.asset.operations)
    if code == 200 and op.method.value == "POST":
        code = 201
    ok = code < 400
    upstream = 5000 if code == 504 else r.randint(40, 420)
    stages = _stages([
        ("Gateway 수신", 2, True),
        ("인증", r.randint(4, 9), code != 401),
        ("구독 확인", 3, code != 403),
        ("한도 확인", 1, code != 429),
        ("대상 API 호출", upstream, code not in (400, 404, 500, 502, 504)),
        ("응답 반환", 2, True),
    ])
    dur = sum(s["ms"] for s in stages)
    provider = c.asset.system
    body = None if op.method.value in ("GET", "DELETE") else {"requestedBy": c.client.code, "qty": r.randint(1, 5)}
    return CallLog(
        tx_id=f"TX-{start.astimezone(KST):%Y%m%d}-{seq:06d}", kind=CallKind.API, success=ok, return_code=str(code), name=c.asset.name,
        asset_id=c.asset.id, subscription_id=c.sub.id, client_system_id=c.client.id, provider_system_id=provider.id, user_id=None,
        started_at=start, ended_at=start + timedelta(milliseconds=dur), duration_ms=dur, client_ip=_ip(c.client),
        protocol="HTTPS", method=op.method.value, uri=f"/{provider.code.lower()}{_fill(op.path, r)}", error_message="" if ok else ERROR_TEXT.get(code, "오류"),
        request_headers={"Authorization": "Bearer ****", "X-A2X-Client-System": c.client.code, "X-A2X-Subscription": str(c.sub.id), "Content-Type": "application/json"},
        request_body=body, response_body={"result": "ok"} if ok else {"code": code, "message": ERROR_TEXT.get(code, "오류")}, stages=stages,
    )


def _mcp_log(c: _Mcp, start: datetime, code: int, r: random.Random, seq: int) -> CallLog:
    ok = code == 200
    upstream = 5000 if code == 504 else r.randint(60, 960)
    stages = _stages([
        ("Gateway 수신", 2, True),
        ("Agent 시스템 인증", 5, True),
        ("시스템 구독 확인", 3, True),
        ("사용자 Tool 권한 확인", 2, code != 403),
        ("MCP 서버 호출", upstream, code not in (500, 502, 504)),
        ("응답 반환", 2, True),
    ])
    dur = sum(s["ms"] for s in stages)
    if code == 403:
        err = f"Tool 권한 없음: {c.tool.name} (신청 상태: {c.status})"
    else:
        err = "" if ok else ERROR_TEXT.get(code, "오류")
    rpc = {"jsonrpc": "2.0", "id": seq, "method": "tools/call", "params": {"name": c.tool.name, "arguments": {}}}
    resp = {"jsonrpc": "2.0", "id": seq, "result": {"content": [{"type": "text", "text": '{"items": 3}'}]}} if ok else \
        {"jsonrpc": "2.0", "id": seq, "error": {"code": -32001 if code == 403 else -32603, "message": err}}
    return CallLog(
        tx_id=f"MCP-{start.astimezone(KST):%Y%m%d}-{seq:06d}", kind=CallKind.MCP, success=ok, return_code=str(code), name=f"{c.asset.name} · {c.tool.name}",
        asset_id=c.asset.id, tool_id=c.tool.id, subscription_id=c.sub.id, client_system_id=c.sub.client_system_id, provider_system_id=c.asset.system_id, user_id=c.user_id,
        started_at=start, ended_at=start + timedelta(milliseconds=dur), duration_ms=dur, client_ip=_ip(c.sub.client_system),
        protocol="MCP", method="tools/call", uri=c.asset.endpoint or f"{GW}/mcp/{c.asset.id}", error_message=err,
        request_headers={"Authorization": "Bearer ****", "X-A2X-Client-System": c.sub.client_system.code, "X-A2X-User": c.user_email},
        request_body=rpc, response_body=resp, stages=stages,
    )


def clear(db: Session) -> int:
    res = db.execute(delete(CallLog).where(or_(*[CallLog.tx_id.like(f"{p}%") for p in PREFIXES])))
    return res.rowcount or 0


def generate(db: Session, days: int = 60, seed: int = 20261125, now: datetime | None = None, api_per_day: int = 140, mcp_per_day: int = 60) -> dict[str, int]:
    """지난 days일의 호출 로그를 만든다(오늘은 now까지). 반환: 종류별 건수."""
    r = random.Random(seed)
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    apis, mcps = _load(db)
    allowed = [m for m in mcps if m.approved]
    denied = [m for m in mcps if not m.approved]
    logs: list[CallLog] = []
    seq = 0

    # 사건 대상: 연계가 가장 많은 API 프로바이더(504 집중), 첫 API 연계(429 반복)
    incident_provider = max({c.asset.system_id for c in apis}, key=lambda sid: sum(c.asset.system_id == sid for c in apis)) if apis else None
    throttled = apis[0] if apis else None

    for back in range(days - 1, -1, -1):
        day = (now - timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)
        scale = 0.35 if day.weekday() >= 5 else 1.0
        growth = 1 + (days - back) / days  # MCP 사용 증가 추세(처음 1배 → 마지막 2배)
        for _ in range(int(api_per_day * scale * r.uniform(0.85, 1.15))):
            t = _pick_time(day, r)
            if t > now or not apis:
                continue
            c = r.choice(apis)
            code = r.choices([x for x, _ in API_CODES], weights=[w for _, w in API_CODES])[0]
            seq += 1
            logs.append(_api_log(c, t.astimezone(timezone.utc), code, r, seq))
        for _ in range(int(mcp_per_day * scale * growth * r.uniform(0.85, 1.15))):
            t = _pick_time(day, r)
            if t > now or not allowed:
                continue
            if denied and r.random() < 0.02:
                c, code = r.choice(denied), 403
            else:
                c = r.choice(allowed)
                code = r.choices([200, 500, 504], weights=[985, 5, 10])[0]
            seq += 1
            logs.append(_mcp_log(c, t.astimezone(timezone.utc), code, r, seq))
        if back == 2 and incident_provider is not None:  # 이틀 전 10시대 한 프로바이더의 504 집중(대상 시스템 장애)
            victims = [c for c in apis if c.asset.system_id == incident_provider]
            for _ in range(18):
                t = day.replace(hour=10, minute=r.randint(0, 59), second=r.randint(0, 59))
                seq += 1
                logs.append(_api_log(r.choice(victims), t.astimezone(timezone.utc), 504 if r.random() < 0.85 else 200, r, seq))
        if back == 1 and throttled is not None:  # 어제 14시대 한 연계의 429 반복
            for _ in range(12):
                t = day.replace(hour=14, minute=r.randint(0, 59), second=r.randint(0, 59))
                seq += 1
                logs.append(_api_log(throttled, t.astimezone(timezone.utc), 429, r, seq))

    db.add_all(logs)
    db.flush()
    return {"api": sum(lg.kind == CallKind.API for lg in logs), "mcp": sum(lg.kind == CallKind.MCP for lg in logs), "errors": sum(not lg.success for lg in logs)}


def main() -> None:
    from src.shared.db.session import SessionLocal

    parser = argparse.ArgumentParser(description="A2X 모니터링 샘플 호출 로그 생성")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--reset", action="store_true", help="생성기가 만든 기존 로그를 지우고 다시 만든다")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.reset:
            print("기존 샘플 로그 삭제:", clear(db))
        elif db.query(CallLog).filter(or_(*[CallLog.tx_id.like(f"{p}%") for p in PREFIXES])).first():
            print("이미 샘플 호출 로그가 있습니다. 다시 만들려면 --reset을 붙이세요.")
            return
        counts = generate(db, days=args.days)
        db.commit()
    print(f"호출 로그 생성 완료: API {counts['api']}건, MCP {counts['mcp']}건(실패 {counts['errors']}건)")


if __name__ == "__main__":
    main()
