"""인증 도메인 저장소."""

from __future__ import annotations

from sqlalchemy import or_, select

from src.auth.models import User
from src.shared.db.repository import Repository, _like


class UserRepository(Repository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.lower().strip()))

    def get_by_google_sub(self, sub: str) -> User | None:
        return self.session.scalar(select(User).where(User.google_sub == sub))

    def search(self, q: str | None = None, limit: int = 20) -> list[User]:
        """사용 중인 사용자를 이름 · 이메일로 찾는다(이름순)."""
        stmt = select(User).where(User.is_active.is_(True))
        if q and q.strip():
            stmt = stmt.where(or_(User.name.ilike(_like(q)), User.email.ilike(_like(q))))
        return [*self.session.scalars(stmt.order_by(User.name, User.email).limit(limit))]
