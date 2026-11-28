"""T1-4 Google 로그인: state 쿠키 · 사용자 연결 규칙 · 콜백 흐름. Google 통신은 가짜 클라이언트로 바꾼다."""

from urllib.parse import parse_qs, urlparse

import pytest

from src.audit.models import AuditLog
from src.auth import google as google_auth
from src.auth.google import GoogleAuthError, GoogleOAuth, pack_state, unpack_state
from src.auth.models import AuthProvider, Role, User
from src.auth.repository import UserRepository
from src.auth.router import get_google
from src.main import app
from src.shared.config import settings


class FakeGoogle:
    def __init__(self, info=None, fail=None):
        self.info, self.fail, self.calls = info or {}, fail, []

    def authorization_url(self):
        return "https://accounts.google.com/o/oauth2/v2/auth?client_id=x&state=STATE123", "STATE123", "VERIFIER456"

    async def fetch_userinfo(self, code, verifier):
        self.calls.append((code, verifier))
        if self.fail:
            raise GoogleAuthError(self.fail)
        return self.info


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:5173/")


@pytest.fixture()
def flow(client, configured):
    def run(info=None, fail=None, state="STATE123", cookie=True, params=None):
        fake = FakeGoogle(info, fail)
        app.dependency_overrides[get_google] = lambda: fake
        client.cookies.clear()
        r = client.get("/api/v1/auth/google/login", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("https://accounts.google.com/")
        if not cookie:
            client.cookies.clear()
        q = params if params is not None else {"code": "CODE789", "state": state}
        r = client.get("/api/v1/auth/google/callback", params=q, follow_redirects=False)
        app.dependency_overrides.pop(get_google, None)
        return r, fake

    return run


def err_of(r):
    return parse_qs(urlparse(r.headers["location"]).query).get("login_error", [None])[0]


def test_state_cookie_signing():
    c = pack_state("abc", "verifier", now=1000)
    assert unpack_state(c, "abc", now=1100) == "verifier"
    for cookie, state, now, code in [(c, "zzz", 1100, "state_invalid"), (c, "abc", 1000 + 601, "state_expired"),
                                     (c[:-1] + ("0" if c[-1] != "0" else "1"), "abc", 1100, "state_invalid"), (None, "abc", 1100, "state_missing")]:
        with pytest.raises(GoogleAuthError) as e:
            unpack_state(cookie, state, now=now)
        assert e.value.code == code


def test_authorization_url_uses_pkce(configured):
    url, state, verifier = GoogleOAuth("cid", "sec", "http://localhost:8000/api/v1/auth/google/callback").authorization_url()
    q = parse_qs(urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"][0] and q["state"] == [state] and len(verifier) >= 43
    assert q["scope"] == ["openid email profile"] and q["redirect_uri"] == ["http://localhost:8000/api/v1/auth/google/callback"]


def test_providers(client, configured, monkeypatch):
    assert client.get("/api/v1/auth/providers").json()["google"] is True
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)
    assert client.get("/api/v1/auth/providers").json()["google"] is False
    r = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert err_of(r) == "google_not_configured"


def test_new_google_user_signs_up_and_gets_session(client, flow, seeded):
    r, fake = flow({"sub": "g-new-1", "email": "New.Person@Gmail.com", "email_verified": True, "name": "새 사용자"})
    assert r.status_code == 303 and r.headers["location"] == "http://localhost:5173/" and err_of(r) is None
    assert fake.calls == [("CODE789", "VERIFIER456")]  # PKCE verifier가 쿠키를 거쳐 전달됨
    me = client.get("/api/v1/auth/me").json()  # 세션 쿠키로 로그인됨
    assert me["user"]["email"] == "new.person@gmail.com" and me["effective_role"] == "USER"
    u = UserRepository(seeded).get_by_email("new.person@gmail.com")
    seeded.refresh(u)
    assert u.auth_provider == AuthProvider.GOOGLE and u.google_sub == "g-new-1" and u.password_hash is None and u.role == Role.USER


def test_existing_email_is_linked(client, flow, seeded):
    r, _ = flow({"sub": "g-kim", "email": "kim@example.com", "email_verified": True, "name": "김민수"})
    assert err_of(r) is None and client.get("/api/v1/auth/me").json()["user"]["email"] == "kim@example.com"
    seeded.expire_all()
    u = UserRepository(seeded).get_by_email("kim@example.com")
    assert u.google_sub == "g-kim" and u.auth_provider == AuthProvider.LOCAL  # 비밀번호 로그인도 계속 가능
    assert seeded.query(AuditLog).filter(AuditLog.action == "user.google_link", AuditLog.actor_id == u.id).count() == 1
    r, _ = flow({"sub": "g-kim", "email": "kim@example.com", "email_verified": True})  # 두 번째는 sub로 바로 찾음
    assert err_of(r) is None


def test_rejections(flow, seeded, monkeypatch):
    assert err_of(flow({"sub": "g1", "email": "a@x.com", "email_verified": False})[0]) == "google_email_unverified"
    assert err_of(flow({"sub": "g1", "email": "a@x.com", "email_verified": True}, state="WRONG")[0]) == "state_invalid"
    assert err_of(flow({"sub": "g1", "email": "a@x.com", "email_verified": True}, cookie=False)[0]) == "state_missing"
    assert err_of(flow(fail="token_exchange_failed")[0]) == "token_exchange_failed"
    assert err_of(flow(params={"error": "access_denied"})[0]) == "google_denied"
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", ["example.com"])
    assert err_of(flow({"sub": "g2", "email": "b@gmail.com", "email_verified": True})[0]) == "google_domain_not_allowed"
    # 이미 다른 Google 계정이 연결된 이메일
    u = UserRepository(seeded).get_by_email("hong@example.com")
    u.google_sub = "g-hong-original"
    seeded.commit()
    assert err_of(flow({"sub": "g-other", "email": "hong@example.com", "email_verified": True})[0]) == "google_account_mismatch"
    assert seeded.query(User).filter(User.google_sub == "g1").count() == 0  # 실패 시 사용자를 만들지 않음


def test_inactive_user_blocked(flow, seeded):
    u = UserRepository(seeded).get_by_email("kim@example.com")
    u.is_active = False
    seeded.commit()
    assert err_of(flow({"sub": "g-kim2", "email": "kim@example.com", "email_verified": True})[0]) == "user_inactive"


def test_configured_flag(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    assert not google_auth.configured()
