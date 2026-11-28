"""Google 로그인 (T1-4): OAuth 2.0 인가 코드 + PKCE, 사용자 정보는 Google userinfo 엔드포인트에서 받는다.

- Authlib의 httpx 클라이언트를 쓴다(Starlette 통합은 세션 미들웨어 · itsdangerous가 필요해 쓰지 않음).
- state · PKCE code_verifier는 서명한 짧은 수명 쿠키에 담는다(HMAC-SHA256, SECRET_KEY). 콜백에서 state가 맞아야 진행한다.
- ID 토큰 서명 검증 대신, 토큰 엔드포인트에서 서버끼리(TLS) 받은 access token으로 userinfo를 조회한다.
- 사내 IdP로 바꿀 때는 이 모듈(엔드포인트 · 클레임 매핑)만 바꾼다. 사용자 연결 규칙(login_with_google)은 공통.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from authlib.common.security import generate_token
from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy.orm import Session

from src.audit.repository import AuditRepository
from src.auth.models import AuthProvider, Role, User
from src.auth.repository import UserRepository
from src.shared.config import settings
from src.shared.errors import Forbidden, Unauthorized

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "openid email profile"
STATE_COOKIE = "a2x_oauth"
STATE_TTL = 600  # 초


class GoogleAuthError(Exception):
    """콜백 처리 실패. code는 화면 안내용(login_error=code)."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


# ---------- state 쿠키 (서명) ----------

def _sign(raw: bytes) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()


def pack_state(state: str, verifier: str, now: float | None = None) -> str:
    raw = base64.urlsafe_b64encode(json.dumps({"s": state, "v": verifier, "t": int(now or time.time())}).encode())
    return f"{raw.decode()}.{_sign(raw)}"


def unpack_state(cookie: str | None, state: str | None, now: float | None = None) -> str:
    """쿠키 서명 · 만료 · state 일치를 확인하고 code_verifier를 돌려준다."""
    if not cookie or not state or "." not in cookie:
        raise GoogleAuthError("state_missing")
    raw, sig = cookie.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(raw.encode())):
        raise GoogleAuthError("state_invalid")
    data = json.loads(base64.urlsafe_b64decode(raw.encode()))
    if (now or time.time()) - data["t"] > STATE_TTL:
        raise GoogleAuthError("state_expired")
    if not hmac.compare_digest(data["s"], state):
        raise GoogleAuthError("state_invalid")
    return data["v"]


# ---------- Google 통신 ----------

@dataclass
class GoogleOAuth:
    client_id: str
    client_secret: str
    redirect_uri: str

    def _client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(self.client_id, self.client_secret, scope=SCOPE, redirect_uri=self.redirect_uri,
                                 code_challenge_method="S256", timeout=10)

    def authorization_url(self) -> tuple[str, str, str]:
        """(Google 인가 URL, state, code_verifier)"""
        verifier = generate_token(64)
        url, state = self._client().create_authorization_url(AUTH_URL, code_verifier=verifier, prompt="select_account")
        return url, state, verifier

    async def fetch_userinfo(self, code: str, verifier: str) -> dict[str, Any]:
        async with self._client() as client:
            try:
                await client.fetch_token(TOKEN_URL, code=code, code_verifier=verifier)
                r = await client.get(USERINFO_URL)
            except Exception as e:  # noqa: BLE001 - 네트워크 · 토큰 교환 오류를 한 가지로 묶는다
                raise GoogleAuthError("token_exchange_failed", f"{type(e).__name__}") from e
        if r.status_code != 200:
            raise GoogleAuthError("userinfo_failed", f"HTTP {r.status_code}")
        return r.json()


def default_client() -> GoogleOAuth:
    return GoogleOAuth(settings.GOOGLE_CLIENT_ID or "", settings.GOOGLE_CLIENT_SECRET or "", settings.GOOGLE_REDIRECT_URI)


# ---------- 사용자 연결 규칙 (코드 판정) ----------

def login_with_google(db: Session, info: dict[str, Any]) -> User:
    """Google 계정 → 포탈 사용자.
    1) google_sub로 찾는다 2) 없으면 같은 이메일의 기존 사용자에 연결한다 3) 없으면 일반 사용자로 즉시 가입.
    Google이 확인한 이메일만 받는다. GOOGLE_ALLOWED_DOMAINS가 있으면 그 도메인만.
    """
    sub, email = str(info.get("sub") or ""), str(info.get("email") or "").strip().lower()
    if not sub or not email:
        raise Unauthorized("Google 계정 정보를 받지 못했습니다.", "google_profile_missing")
    if info.get("email_verified") is not True:
        raise Unauthorized("Google에서 확인되지 않은 이메일입니다.", "google_email_unverified")
    domain = email.rsplit("@", 1)[-1]
    allowed = [d.lower() for d in settings.GOOGLE_ALLOWED_DOMAINS]
    if allowed and domain not in allowed:
        raise Forbidden(f"허용되지 않은 도메인입니다({domain}).", "google_domain_not_allowed")

    users, audit = UserRepository(db), AuditRepository(db)
    user = users.get_by_google_sub(sub)
    if user is None:
        user = users.get_by_email(email)
        if user is not None:
            if user.google_sub and user.google_sub != sub:
                raise Unauthorized("이 이메일은 다른 Google 계정에 연결되어 있습니다.", "google_account_mismatch")
            user.google_sub = sub
            audit.record(user.id, "user.google_link", "user", user.id)
        else:
            name = str(info.get("name") or email.split("@")[0])[:100]
            user = users.add(User(email=email, name=name, role=Role.USER, auth_provider=AuthProvider.GOOGLE, google_sub=sub))
            audit.record(user.id, "user.signup", "user", user.id, {"provider": "GOOGLE"})
    if not user.is_active:
        raise Forbidden("사용이 중지된 계정입니다.", "user_inactive")
    audit.record(user.id, "user.login", "user", user.id, {"provider": "GOOGLE"})
    db.flush()
    return user
