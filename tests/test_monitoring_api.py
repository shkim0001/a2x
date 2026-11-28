"""T2-4 모니터링 API: 조회 범위 · 상세 · 통계 · 요약 (생성기로 만든 최근 7일 호출 로그)."""

import pytest

from src.monitoring.generator import generate


@pytest.fixture()
def data(client, seeded):
    generate(seeded, days=7)
    seeded.commit()
    return client


def calls(client, headers, **params):
    return client.get("/api/v1/monitoring/calls", params=params, headers=headers).json()


def all_calls(client, headers, **params):
    """모든 페이지를 모은다."""
    out, page = [], 1
    while True:
        r = calls(client, headers, page=page, size=200, **params)
        out += r["items"]
        if page * r["size"] >= r["total"]:
            return out
        page += 1


def test_calls_scope_by_role(data, as_user):
    admin = all_calls(data, as_user("admin@example.com"))
    hong = all_calls(data, as_user("hong@example.com"))
    kim = all_calls(data, as_user("kim@example.com"))
    assert len(admin) > len(hong) > len(kim) > 0
    assert all({r["client_system"]["code"], r["provider_system"]["code"]} & {"WMS", "CSBOT"} or r["user"] == "홍길동" for r in hong)
    assert all(r["kind"] == "MCP" and r["user"] for r in kim) and len({r["user"] for r in kim}) == 1  # 일반 사용자는 내 Tool 호출만
    assert admin[0]["started_at"] >= admin[-1]["started_at"]  # 최신순


def test_calls_paging(data, as_user):
    h = as_user("admin@example.com")
    first, second = calls(data, h, page=1, size=20), calls(data, h, page=2, size=20)
    assert first["total"] > 40 and len(first["items"]) == 20 and len(second["items"]) == 20
    assert {r["tx_id"] for r in first["items"]}.isdisjoint({r["tx_id"] for r in second["items"]})  # 페이지끼리 겹치지 않음
    assert first["items"][-1]["started_at"] >= second["items"][0]["started_at"]  # 최신순이 이어진다
    last = (first["total"] - 1) // 20 + 1
    assert len(calls(data, h, page=last, size=20)["items"]) == first["total"] - (last - 1) * 20
    assert calls(data, h, page=last + 1, size=20)["items"] == []
    assert data.get("/api/v1/monitoring/calls?size=500", headers=h).status_code == 422  # 한 페이지 최대 200


def test_calls_filters(data, as_user):
    h = as_user("admin@example.com")
    failed = calls(data, h, kind="API", status="failed")
    assert failed["total"] and all(not r["success"] and r["kind"] == "API" for r in failed["items"])
    ok = calls(data, h, kind="MCP", status="success", size=50)
    assert ok["total"] and all(r["success"] and r["kind"] == "MCP" for r in ok["items"])
    assert failed["total"] + calls(data, h, kind="API", status="success")["total"] == calls(data, h, kind="API")["total"]
    q = all_calls(data, h, q="WMS")
    assert q and all("WMS" in (r["client_system"]["name"] + r["provider_system"]["name"] + r["uri"].upper()) for r in q)
    hong_calls = all_calls(data, h, q="홍길동")  # 사용자 이름으로도 찾는다
    assert hong_calls and all(r["user"] == "홍길동" for r in hong_calls)


def test_call_detail_and_scope(data, as_user):
    admin = as_user("admin@example.com")
    row = calls(data, admin, kind="API", status="failed", size=1)["items"][0]
    d = data.get(f"/api/v1/monitoring/calls/{row['tx_id']}", headers=admin).json()
    assert d["stages"] and d["classification"]["category"] and d["request_headers"]["Authorization"] == "Bearer ****"
    # API 호출(사용자 없음)은 일반 사용자 범위 밖
    assert data.get(f"/api/v1/monitoring/calls/{row['tx_id']}", headers=as_user("kim@example.com")).status_code == 404


def test_stats_daily_monthly(data, as_user):
    h = as_user("admin@example.com")
    daily = data.get("/api/v1/monitoring/stats?unit=daily", headers=h).json()
    assert len(daily) == 30 and sum(r["api"] + r["mcp"] for r in daily[-7:]) > 0 and daily[0]["api"] == 0  # 7일치만 생성
    monthly = data.get("/api/v1/monitoring/stats?unit=monthly", headers=h).json()
    assert len(monthly) == 12 and sum(r["api"] + r["mcp"] for r in monthly) == sum(r["api"] + r["mcp"] for r in daily)


def test_summary(data, as_user):
    s = data.get("/api/v1/monitoring/summary", headers=as_user("admin@example.com")).json()
    assert s["failed_24h"] > 0 and len(s["recent_errors"]) <= 3 and s["recent_errors"][0]["count"] >= s["recent_errors"][-1]["count"]
    assert 0 <= s["today_error_rate"] <= 100


# ---------- 기간 조회(날짜 · 시간) ----------


def test_calls_period_filter(data, as_user):
    from datetime import datetime, timedelta, timezone

    h = as_user("admin@example.com")
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst).replace(second=0, microsecond=0)
    week = calls(data, h, size=1)["total"]
    # 최근 하루(시간대 없는 시각은 KST로 본다)
    day = calls(data, h, size=200, start=(now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"), end=now.strftime("%Y-%m-%dT%H:%M"))
    assert 0 < day["total"] < week
    start = (now - timedelta(days=1)).astimezone(timezone.utc)
    for r in day["items"]:
        assert datetime.fromisoformat(r["started_at"]).replace(tzinfo=timezone.utc) >= start - timedelta(seconds=1)
    # 끝이 시작보다 앞서면 거절, 기간이 너무 길면 거절
    r = data.get("/api/v1/monitoring/calls", params={"start": "2026-11-25T10:00", "end": "2026-11-25T09:00"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "invalid_period"
    r = data.get("/api/v1/monitoring/calls", params={"start": "2024-01-01T00:00", "end": "2026-01-01T00:00"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "period_too_long"


def test_stats_custom_range(data, as_user):
    from datetime import datetime, timedelta, timezone

    h = as_user("admin@example.com")
    today = datetime.now(timezone(timedelta(hours=9))).date()
    rows = data.get("/api/v1/monitoring/stats", params={"unit": "daily", "start": str(today - timedelta(days=2)), "end": str(today)}, headers=h).json()
    assert [r["key"] for r in rows] == [str(today - timedelta(days=i)) for i in (2, 1, 0)]
    assert sum(r["api"] + r["mcp"] for r in rows) > 0
    m = data.get("/api/v1/monitoring/stats", params={"unit": "monthly", "start": "2026-09-15", "end": "2026-11-02"}, headers=h).json()
    assert [r["key"] for r in m] == ["2026-09", "2026-10", "2026-11"]
    r = data.get("/api/v1/monitoring/stats", params={"unit": "daily", "start": str(today), "end": str(today - timedelta(days=1))}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "invalid_period"


def test_mcp_calls_show_caller_login_id(data, as_user):
    rows = calls(data, as_user("admin@example.com"), kind="MCP", size=200)["items"]
    with_user = [r for r in rows if r["user"]]
    assert with_user and all("@" in r["user_login"] for r in with_user)  # 실제로 호출한 사용자의 로그인 ID
