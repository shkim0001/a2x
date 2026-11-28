"""API 의존성: DB 세션, 현재 사용자, 역할 확인."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.auth.models import Role, User
from src.auth.service import resolve_session
from src.shared.db.session import get_db
from src.shared.errors import Forbidden, Unauthorized

SESSION_COOKIE = "a2x_session"


def read_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    return resolve_session(db, read_token(request))


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise Unauthorized("로그인이 필요합니다.", "login_required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise Forbidden("admin만 할 수 있습니다.", "admin_only")
    return user
