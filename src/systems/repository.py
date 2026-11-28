"""기준정보 도메인 저장소."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from src.auth.models import User
from src.shared.db.repository import _like, Repository
from src.systems.models import Server, System, SystemManager


class SystemRepository(Repository[System]):
    model = System

    def get_by_code(self, code: str) -> System | None:
        return self.session.scalar(select(System).where(System.code == code.upper()))

    def search(self, q: str | None = None, kind: Any = None, process: str | None = None, managed_by: int | None = None) -> list[System]:
        stmt = select(System)
        if q:
            # 이름(영문) · 코드 · 부서 · 업무 프로세스(한글)로 찾는다
            stmt = stmt.where(or_(System.name.ilike(_like(q)), System.code.ilike(_like(q)), System.dept.ilike(_like(q)), System.process.ilike(_like(q))))
        if kind:
            stmt = stmt.where(System.kind == kind)
        if process:
            stmt = stmt.where(System.process == process)
        if managed_by is not None:
            stmt = stmt.join(SystemManager).where(SystemManager.user_id == managed_by)
        return [*self.session.scalars(stmt.order_by(System.id)).unique()]

    def managed_ids(self, user_id: int) -> set[int]:
        return set(self.session.scalars(select(SystemManager.system_id).where(SystemManager.user_id == user_id)))

    def add_manager(self, system: System, user: User) -> bool:
        """이미 담당자면 False. 담당자 추가는 승인 없이 바로 반영한다."""
        if system.is_manager(user.id):
            return False
        system.managers.append(SystemManager(user_id=user.id, user=user))
        self.session.flush()
        return True


class ServerRepository(Repository[Server]):
    model = Server
