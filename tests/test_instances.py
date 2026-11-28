"""인스턴스 모니터링: 구성요소 상태 판정(네트워크 점검은 가짜로 바꿔 끼운다)."""

import anyio
import pytest

from src.monitoring import health

API = "/api/v1/monitoring/instances"


def fake_probe(down: set[str] = frozenset()):
    async def probe(client, url, mcp=False, want_json=False):
        if any(k in url for k in down):
            return False, None, None, None, "연결 실패(ConnectError)"
        body = {"status": "ok", "uptime_s": 60, "enforce_permissions": True, "policy_db": "ok", "policy_db_ms": 1} if url.endswith("/health") else None
        return True, 12, 200, body, ""

    return probe


@pytest.fixture(autouse=True)
def no_cache():
    health._cache.clear()
    yield
    health._cache.clear()


def comp(data, key):
    return next(c for g in data["groups"] for c in g["components"] if c["key"] == key)


def test_worst_ignores_off():
    assert health.worst(["ok", "off"]) == "ok"
    assert health.worst(["off", "off"]) == "off"
    assert health.worst(["ok", "warn", "down"]) == "down"


def test_all_reachable(seeded, monkeypatch):
    monkeypatch.setattr(health, "probe", fake_probe())
    d = anyio.run(lambda: health.check_all(seeded, use_cache=False))
    assert {g["key"] for g in d["groups"]} == {"portal", "perm-gw", "data-gw", "mcp-servers", "external", "agent", "ops"}
    assert comp(d, "runtime")["status"] == "ok" and comp(d, "policy")["status"] == "ok"
    assert comp(d, "wso2")["status"] == "off"  # 미도입은 비정상이 아니다
    # 시드의 예시 도메인(.example) MCP는 점검 제외, IRP · DCM(localhost)은 실제 점검
    servers = {c["name"]: c for c in next(g for g in d["groups"] if g["key"] == "mcp-servers")["components"]}
    assert servers["재고 MCP 서버"]["status"] == "off" and servers["IRP 시스템 정보 MCP"]["status"] == "ok"
    assert d["status"] != "down"


def test_runtime_down_marks_gateways_and_converted_mcp(seeded, monkeypatch):
    monkeypatch.setattr(health, "probe", fake_probe(down={":8100"}))
    d = anyio.run(lambda: health.check_all(seeded, use_cache=False))
    assert comp(d, "runtime")["status"] == "down" and comp(d, "policy")["status"] == "down"
    converted = [c for g in d["groups"] if g["key"] == "mcp-servers" for c in g["components"] if c["kind"] == "변환 MCP"]
    assert converted and all(c["status"] == "down" for c in converted)
    assert d["status"] == "down" and d["counts"]["down"] >= 3
    # 비정상 MCP 서버가 묶음의 맨 앞에 온다
    assert next(g for g in d["groups"] if g["key"] == "mcp-servers")["components"][0]["status"] == "down"


def test_external_mcp_down(seeded, monkeypatch):
    monkeypatch.setattr(health, "probe", fake_probe(down={"/irp/mcp"}))
    d = anyio.run(lambda: health.check_all(seeded, use_cache=False))
    assert comp(d, "irp")["status"] == "down" and comp(d, "dcm")["status"] == "ok"


def test_api_permissions(client, as_user, monkeypatch):
    monkeypatch.setattr(health, "probe", fake_probe())
    assert client.get(API, headers=as_user("lee@example.com")).status_code == 403  # 담당 시스템 없는 사용자
    r = client.get(API, headers=as_user("hong@example.com"))
    assert r.status_code == 200 and r.json()["groups"]
    assert client.get(API + "?refresh=true", headers=as_user("admin@example.com")).status_code == 200
