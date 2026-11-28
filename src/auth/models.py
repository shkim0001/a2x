"""인증 도메인 모델: 사용자 · 로그인 세션과 역할 · 인증 수단 코드값."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base, enum_type, TimestampMixin

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from enum import StrEnum


class Role(StrEnum):
    """저장하는 역할은 admin 여부뿐이다. '시스템 담당자'는 담당 시스템이 있는지로 계산한다(systems.access.effective_role).
    DB의 CHECK 제약에는 예전 값 MANAGER가 남아 있지만 쓰지 않는다(마이그레이션에서 USER로 바꿈)."""

    USER = "USER"
    ADMIN = "ADMIN"


class AuthProvider(StrEnum):
    LOCAL = "LOCAL"
    GOOGLE = "GOOGLE"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(enum_type(Role, "user_role"), default=Role.USER)
    auth_provider: Mapped[AuthProvider] = mapped_column(enum_type(AuthProvider, "auth_provider"), default=AuthProvider.LOCAL)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # Google 사용자는 비어 있다
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email} {self.role}>"


class AuthSession(Base):
    """로그인 세션. 토큰 원문은 저장하지 않고 SHA-256 해시만 둔다(DB가 새도 토큰을 쓸 수 없게)."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_agent: Mapped[str] = mapped_column(String(300), default="")

    user: Mapped[User] = relationship(lazy="joined")


