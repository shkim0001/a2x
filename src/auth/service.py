"""자체 가입 · 로그인 · 로그아웃 · 세션 확인.

인증 방식을 사내 IdP로 바꿔도 이 서비스의 resolve_session / 사용자 모델은 그대로 쓴다.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.audit.repository import AuditRepository
from src.auth.models import AuthProvider, AuthSession, Role, User
from src.auth.repository import UserRepository
from src.auth.security import BCRYPT_MAX_BYTES, DUMMY_HASH, hash_password, hash_token, new_token, verify_password
from src.shared.config import dev_role_switch_enabled, settings
from src.shared.errors import Conflict, Forbidden, Invalid, Unauthorized

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    # SQLite는 시간대 정보를 버리므로 UTC로 간주한다
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def validate_signup(email: str, name: str, password: str) -> tuple[str, str]:
    email = email.strip().lower()
    name = name.strip()
    if not EMAIL_RE.match(email):
        raise Invalid("이메일 형식이 올바르지 않습니다.", "invalid_email")
    if not name:
        raise Invalid("이름을 입력하세요.", "invalid_name")
    if len(password) < MIN_PASSWORD:
        raise Invalid(f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다.", "weak_password")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise Invalid(f"비밀번호는 {BCRYPT_MAX_BYTES}바이트 이하여야 합니다.", "password_too_long")
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise Invalid("비밀번호에 영문과 숫자를 함께 넣어 주세요.", "weak_password")
    return email, name


def signup(db: Session, email: str, name: str, password: str) -> User:
    """즉시 가입. 새 사용자는 일반 사용자이며, 시스템 담당자로 지정되면 담당자 역할이 된다."""
    email, name = validate_signup(email, name, password)
    users = UserRepository(db)
    if users.get_by_email(email):
        raise Conflict("이미 가입된 이메일입니다.", "email_taken")
    user = users.add(User(email=email, name=name, role=Role.USER, auth_provider=AuthProvider.LOCAL, password_hash=hash_password(password)))
    AuditRepository(db).record(user.id, "user.signup", "user", user.id)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = UserRepository(db).get_by_email(email)
    if user is None or not user.is_active or not user.password_hash:
        verify_password(password, DUMMY_HASH)  # 시간 차로 계정 존재 여부가 드러나지 않게
        raise Unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.", "invalid_credentials")
    if not verify_password(password, user.password_hash):
        raise Unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.", "invalid_credentials")
    return user


def create_session(db: Session, user: User, user_agent: str = "") -> tuple[str, AuthSession]:
    token = new_token()
    s = AuthSession(
        token_hash=hash_token(token),
        user_id=user.id,
        expires_at=_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        user_agent=user_agent[:300],
    )
    db.add(s)
    db.flush()
    AuditRepository(db).record(user.id, "user.login", "user", user.id)
    return token, s


def resolve_session(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if s is None or _aware(s.expires_at) <= _now() or not s.user.is_active:
        return None
    return s.user


def logout(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))


def purge_expired(db: Session) -> int:
    return db.execute(delete(AuthSession).where(AuthSession.expires_at <= _now())).rowcount or 0


def switch_role_dev(db: Session, user: User, role: Role) -> User:
    """개발용 권한 스위치: 로그인한 사용자가 admin ↔ 일반을 바꾼다. 개발 환경에서만 허용(운영에서는 403).
    시스템 담당자는 저장하는 역할이 아니라 담당 시스템 유무로 계산되므로 스위치 대상이 아니다.
    """
    if not dev_role_switch_enabled():
        raise Forbidden("권한 스위치는 개발 환경에서만 쓸 수 있습니다.", "dev_only")
    before = user.role
    user.role = role
    AuditRepository(db).record(user.id, "user.role.dev_switch", "user", user.id, {"from": before.value, "to": role.value})
    db.flush()
    return user


def search_users(db: Session, user: User, q: str | None, limit: int = 20) -> list[User]:
    """담당자 지정용 사용자 검색(이름 · 이메일만). 누구나 시스템을 등록하며 추가 담당자를 고르므로 로그인한 사용자 모두에게 연다."""
    return UserRepository(db).search(q, limit)
