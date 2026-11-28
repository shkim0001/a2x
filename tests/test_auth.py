from datetime import datetime, timedelta, timezone

from src.auth.models import AuthSession

from tests.conftest import DEV_PASSWORD

API = "/api/v1/auth"


def test_signup_sets_cookie_and_returns_user(client):
    r = client.post(f"{API}/signup", json={"email": "New.User@Example.com", "name": "신규", "password": "abcd1234"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "new.user@example.com"  # 소문자로 저장
    assert body["user"]["role"] == "USER" and body["effective_role"] == "USER"
    assert "a2x_session" in r.cookies
    # 쿠키만으로 /me 조회
    me = client.get(f"{API}/me")
    assert me.status_code == 200 and me.json()["user"]["name"] == "신규"


def test_signup_validation(client):
    cases = [
        ({"email": "bad", "name": "x", "password": "abcd1234"}, "invalid_email"),
        ({"email": "a@b.co", "name": " ", "password": "abcd1234"}, "invalid_name"),
        ({"email": "a@b.co", "name": "x", "password": "short1"}, "weak_password"),
        ({"email": "a@b.co", "name": "x", "password": "onlyletters"}, "weak_password"),
        ({"email": "a@b.co", "name": "x", "password": "가" * 25 + "a1"}, "password_too_long"),  # 77바이트
    ]
    for body, code in cases:
        r = client.post(f"{API}/signup", json=body)
        assert r.status_code == 422 and r.json()["code"] == code, (body, r.text)


def test_signup_duplicate_email(client):
    r = client.post(f"{API}/signup", json={"email": "hong@example.com", "name": "x", "password": "abcd1234"})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"


def test_login_success_and_effective_role(client):
    r = client.post(f"{API}/login", json={"email": "hong@example.com", "password": DEV_PASSWORD})
    assert r.status_code == 200
    assert r.json()["effective_role"] == "MANAGER"
    me = client.get(f"{API}/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert len(me.json()["managed_system_ids"]) == 2  # WMS, CS 챗봇


def test_login_failures_do_not_reveal_account(client):
    wrong_pw = client.post(f"{API}/login", json={"email": "hong@example.com", "password": "wrong-pass1"})
    no_user = client.post(f"{API}/login", json={"email": "nobody@example.com", "password": "wrong-pass1"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_me_requires_login(client):
    r = client.get(f"{API}/me")
    assert r.status_code == 401 and r.json()["code"] == "login_required"
    assert client.get(f"{API}/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_logout_invalidates_token(client):
    token = client.post(f"{API}/login", json={"email": "kim@example.com", "password": DEV_PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get(f"{API}/me", headers=h).status_code == 200
    client.post(f"{API}/logout", headers=h)
    assert client.get(f"{API}/me", headers=h).status_code == 401


def test_expired_session_rejected(client, session_factory):
    token = client.post(f"{API}/login", json={"email": "kim@example.com", "password": DEV_PASSWORD}).json()["token"]
    with session_factory() as s:
        for row in s.query(AuthSession).all():
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        s.commit()
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_stored_as_hash(client, session_factory):
    token = client.post(f"{API}/login", json={"email": "kim@example.com", "password": DEV_PASSWORD}).json()["token"]
    with session_factory() as s:
        hashes = [r.token_hash for r in s.query(AuthSession).all()]
    assert token not in hashes and all(len(h) == 64 for h in hashes)


# ---------- 개발용 권한 스위치 ----------

def test_dev_role_switch(client, as_user, monkeypatch):
    from src.shared.config import settings

    monkeypatch.setattr(settings, "DEV_ROLE_SWITCH", None)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    h = as_user("kim@example.com")
    assert client.get("/api/v1/auth/providers").json()["dev_role_switch"] is True
    r = client.put("/api/v1/auth/dev/role", json={"role": "ADMIN"}, headers=h)
    assert r.status_code == 200 and r.json()["effective_role"] == "ADMIN"
    assert client.put("/api/v1/auth/dev/role", json={"role": "USER"}, headers=h).json()["effective_role"] == "USER"
    # 시스템 담당자는 저장하는 역할이 아니다(담당 시스템 유무로 계산)
    assert client.put("/api/v1/auth/dev/role", json={"role": "MANAGER"}, headers=h).status_code == 422
    assert client.put("/api/v1/auth/dev/role", json={"role": "ROOT"}, headers=h).status_code == 422


def test_manager_role_is_computed_from_managed_systems(client, as_user):
    # 담당 시스템이 생기면 시스템 담당자, 모두 없어지면 다시 일반 사용자(저장 역할은 그대로 USER)
    h = as_user("kim@example.com")
    assert client.get("/api/v1/auth/me", headers=h).json()["effective_role"] == "USER"
    sid = client.post("/api/v1/systems", headers=h, json={"code": "KIMX", "name": "KIMX", "kind": "BUSINESS", "process": "물류"}).json()["id"]
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["effective_role"] == "MANAGER" and me["user"]["role"] == "USER" and sid in me["managed_system_ids"]
    assert client.delete(f"/api/v1/systems/{sid}", headers=h).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).json()["effective_role"] == "USER"


def test_manager_can_request_tools_personally(client, as_user):
    # 담당 시스템이 있어도 개인 Tool 신청은 그대로(연계 목록이 보인다)
    assert client.get("/api/v1/connections", headers=as_user("hong@example.com")).json()


def test_dev_role_switch_disabled_in_production(client, as_user, monkeypatch):
    from src.shared.config import settings

    monkeypatch.setattr(settings, "DEV_ROLE_SWITCH", None)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert client.get("/api/v1/auth/providers").json()["dev_role_switch"] is False
    r = client.put("/api/v1/auth/dev/role", json={"role": "ADMIN"}, headers=as_user("kim@example.com"))
    assert r.status_code == 403 and r.json()["code"] == "dev_only"


# ---------- 사용자 검색(담당자 지정용) ----------

def test_user_search_for_managers(client, as_user):
    h = as_user("hong@example.com")
    r = client.get("/api/v1/users?q=kim@", headers=h)
    assert r.status_code == 200 and [u["email"] for u in r.json()] == ["kim@example.com"]
    assert {u["name"] for u in client.get("/api/v1/users?q=김", headers=h).json()} == {"김민수", "김희령", "김성환"}
    assert set(r.json()[0]) == {"id", "name", "email"}  # 이름 · 이메일만
    assert len(client.get("/api/v1/users", headers=as_user("admin@example.com")).json()) >= 3


def test_user_search_hides_inactive_and_open_to_all_users(client, as_user, seeded):
    from src.auth.repository import UserRepository

    u = UserRepository(seeded).get_by_email("kim@example.com")
    u.is_active = False
    seeded.commit()
    assert client.get("/api/v1/users?q=kim@", headers=as_user("hong@example.com")).json() == []
    u.is_active = True
    seeded.commit()
    # 누구나 시스템을 등록하며 추가 담당자를 고르므로 일반 사용자도 검색할 수 있다(이름 · 이메일만)
    r = client.get("/api/v1/users?q=hong@", headers=as_user("kim@example.com"))
    assert r.status_code == 200 and set(r.json()[0]) == {"id", "name", "email"}
