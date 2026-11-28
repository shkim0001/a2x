"""시스템 · API · MCP 삭제: 연결이 남아 있으면 막고, 끝난 구독 이력은 함께 정리한다."""

from test_registry import API, ADMIN, HONG, KIM, _sys_id, api_body


def _asset(client, h, name):
    return next(a for a in client.get(f"{API}/assets", headers=h).json() if a["name"] == name)


def test_delete_draft_api(client, as_user):
    h = as_user(HONG)
    aid = client.post(f"{API}/assets/api", headers=h, json=api_body(_sys_id(client, h, "WMS"))).json()["id"]
    # 담당자가 아니면 못 지운다
    assert client.delete(f"{API}/assets/{aid}", headers=as_user(KIM)).status_code in (403, 404)
    assert client.delete(f"{API}/assets/{aid}", headers=h).status_code == 200
    assert client.get(f"{API}/assets/{aid}", headers=h).status_code == 404


def test_cannot_delete_asset_with_active_subscription(client, as_user):
    h = as_user(HONG)
    stock = _asset(client, h, "재고 MCP 서버")
    r = client.delete(f"{API}/assets/{stock['id']}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "asset_in_use"


def test_cannot_delete_api_with_converted_mcp(client, as_user):
    admin = as_user(ADMIN)
    assets = client.get(f"{API}/assets", headers=admin).json()
    src_id = next(a["converted_from_id"] for a in assets if a["converted_from_id"])
    # 원본 API에 활성 구독이 있으면 그 사유가 먼저 나올 수 있으므로 둘 중 하나
    r = client.delete(f"{API}/assets/{src_id}", headers=admin)
    assert r.status_code == 409 and r.json()["code"] in ("asset_converted", "asset_in_use")


def test_delete_system_with_servers_and_ended_subscription(client, as_user):
    h = as_user(HONG)
    r = client.post(f"{API}/systems", headers=h, json={
        "code": "TMPX", "name": "TMPX", "kind": "BUSINESS", "process": "물류",
        "servers": [{"hostname": "tmpx-app01", "ip": "10.0.0.1", "port": 8080}],
    })
    sid = r.json()["id"]
    order = _asset(client, h, "주문 조회 API")
    sub = client.post(f"{API}/subscriptions", headers=h, json={"client_system_id": sid, "asset_id": order["id"], "purpose": "시험"}).json()
    # 대기 중인 구독이 있으면 삭제 불가 → 해지 후 삭제
    r = client.delete(f"{API}/systems/{sid}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "system_in_use"
    assert client.post(f"{API}/subscriptions/{sub['id']}/cancel", headers=h).status_code == 200
    assert client.delete(f"{API}/systems/{sid}", headers=as_user(KIM)).status_code == 403
    assert client.delete(f"{API}/systems/{sid}", headers=h).status_code == 200
    assert client.get(f"{API}/systems/{sid}", headers=h).status_code == 404
    assert not [s for s in client.get(f"{API}/servers?q=tmpx", headers=h).json()]


def test_cannot_delete_system_with_assets_or_builtin(client, as_user):
    h, admin = as_user(HONG), as_user(ADMIN)
    r = client.delete(f"{API}/systems/{_sys_id(client, h, 'WMS')}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "system_has_assets"
    r = client.delete(f"{API}/systems/{_sys_id(client, admin, 'A2X')}", headers=admin)
    assert r.status_code == 422 and r.json()["code"] == "builtin_system"


def test_deletes_are_audited(client, as_user, session_factory):
    from sqlalchemy import select

    from src.audit.models import AuditLog

    h = as_user(HONG)
    aid = client.post(f"{API}/assets/api", headers=h, json=api_body(_sys_id(client, h, "WMS"))).json()["id"]
    client.delete(f"{API}/assets/{aid}", headers=h)
    with session_factory() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "asset.delete", AuditLog.target_id == str(aid))) is not None
