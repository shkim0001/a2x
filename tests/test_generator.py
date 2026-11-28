"""T1-2 모니터링 샘플 호출 로그 생성기."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from src.monitoring.generator import clear, generate, KST
from src.monitoring.models import CallKind, CallLog
from src.subscriptions.models import RequestStatus, ToolRequest

NOW = datetime(2026, 11, 25, 15, 0, tzinfo=KST)  # 수요일


def logs(db):
    return db.query(CallLog).order_by(CallLog.id).all()


def test_generates_consistent_rows(seeded):
    counts = generate(seeded, days=14, now=NOW)
    rows = logs(seeded)
    assert counts["api"] > 500 and counts["mcp"] > 200 and len(rows) == counts["api"] + counts["mcp"]
    assert len({r.tx_id for r in rows}) == len(rows)
    for r in rows:
        assert r.ended_at - r.started_at == timedelta(milliseconds=r.duration_ms) and r.duration_ms == sum(s["ms"] for s in r.stages)
        assert r.success == (int(r.return_code) < 400) and (r.error_message == "") == r.success
        assert r.started_at.replace(tzinfo=timezone.utc) <= NOW
        assert r.request_headers["Authorization"] == "Bearer ****"  # 인증 값은 가림
        if r.kind == CallKind.API:
            assert r.user_id is None and r.protocol == "HTTPS"
        else:
            assert r.user_id and r.tool_id and r.method == "tools/call"


def test_mcp_calls_follow_tool_permissions(seeded):
    generate(seeded, days=14, now=NOW)
    approved = {(t.user_id, t.tool_id) for t in seeded.query(ToolRequest).filter(ToolRequest.status == RequestStatus.APPROVED)}
    for r in logs(seeded):
        if r.kind == CallKind.MCP:
            assert ((r.user_id, r.tool_id) in approved) == (r.return_code != "403")


def test_incidents_for_error_agent(seeded):
    generate(seeded, days=14, now=NOW)
    rows = logs(seeded)
    kst = lambda r: r.started_at.replace(tzinfo=timezone.utc).astimezone(KST)
    burst = Counter(r.provider_system_id for r in rows if r.return_code == "504" and kst(r).date() == (NOW - timedelta(days=2)).date() and kst(r).hour == 10)
    assert burst and burst.most_common(1)[0][1] >= 5  # 이틀 전 10시대 한 프로바이더 504 집중
    repeat = Counter(r.subscription_id for r in rows if r.return_code == "429" and kst(r).date() == (NOW - timedelta(days=1)).date())
    assert repeat.most_common(1)[0][1] >= 12  # 어제 한 연계의 429 반복


def test_weekday_more_than_weekend_and_deterministic(seeded):
    generate(seeded, days=14, now=NOW)
    first = [(r.tx_id, r.return_code) for r in logs(seeded)]
    by_day = Counter(r.started_at.replace(tzinfo=timezone.utc).astimezone(KST).weekday() for r in logs(seeded))
    assert by_day[0] > by_day[6] * 2
    assert clear(seeded) == len(first)
    generate(seeded, days=14, now=NOW)
    assert [(r.tx_id, r.return_code) for r in logs(seeded)] == first


def test_clear_keeps_converter_logs(seeded):
    generate(seeded, days=2, now=NOW)
    seeded.add(CallLog(tx_id="CV-real", kind=CallKind.MCP, success=True, return_code="200", name="x", started_at=NOW, ended_at=NOW, duration_ms=0, protocol="MCP", method="tools/call", uri="/"))
    seeded.flush()
    clear(seeded)
    assert [r.tx_id for r in logs(seeded)] == ["CV-real"]
