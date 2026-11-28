"""admin은 모든 시스템의 시스템 구독 · Tool 사용 신청을 승인 · 반려할 수 있다."""

from sqlalchemy import select

API = "/api/v1"


def test_admin_sees_and_decides_all_pending_subscriptions(client, as_user, session_factory):
    from src.audit.models import AuditLog

    admin = as_user("admin@example.com")
    rows = client.get(f"{API}/subscriptions?scope=approve&status=PENDING", headers=admin).json()
    # 시드의 승인 대기 구독(ERP · WMS · MES 등 여러 프로바이더)이 모두 보이고 버튼도 켜진다
    assert len({r["provider_system"]["code"] for r in rows}) >= 2 and all(r["can_decide"] for r in rows)
    sub = rows[0]
    r = client.post(f"{API}/subscriptions/{sub['id']}/approve", headers=admin, json={"note": "admin 승인"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    with session_factory() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.action == "subscription.approve", AuditLog.target_id == str(sub["id"])))
        assert log is not None and log.detail.get("as_admin") is True


def test_admin_decides_tool_requests(client, as_user):
    admin = as_user("admin@example.com")
    rows = client.get(f"{API}/tool-requests?scope=approve&status=PENDING", headers=admin).json()
    assert rows and all(r["can_decide"] for r in rows)
    r = client.post(f"{API}/tool-requests/{rows[0]['id']}/reject", headers=admin, json={"note": "목적 불명확"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"


def test_non_manager_still_cannot_decide(client, as_user):
    admin = as_user("admin@example.com")
    sub = client.get(f"{API}/subscriptions?scope=approve&status=PENDING", headers=admin).json()[0]
    r = client.post(f"{API}/subscriptions/{sub['id']}/approve", headers=as_user("lee@example.com"))
    assert r.status_code == 403 and r.json()["code"] == "not_provider_manager"
