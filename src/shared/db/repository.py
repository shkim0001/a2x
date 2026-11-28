"""저장소 기반 클래스와 공용 조회 헬퍼. 도메인 저장소는 각 도메인의 repository.py."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.shared.db.base import Base

from typing import Any

from sqlalchemy import select


M = TypeVar("M", bound=Base)


class Repository(Generic[M]):
    model: type[M]

    def __init__(self, session: Session):
        self.session = session

    def get(self, id_: Any) -> M | None:
        return self.session.get(self.model, id_)

    def list(self, *where: Any, order_by: Any = None, limit: int | None = None, offset: int = 0) -> list[M]:
        stmt = select(self.model).where(*where)
        if order_by is not None:
            stmt = stmt.order_by(*(order_by if isinstance(order_by, (list, tuple)) else [order_by]))
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        return [*self.session.scalars(stmt).unique()]

    def count(self, *where: Any) -> int:
        return self.session.scalar(select(func.count()).select_from(self.model).where(*where)) or 0

    def add(self, obj: M) -> M:
        self.session.add(obj)
        self.session.flush()
        return obj

    def add_all(self, objs: Sequence[M]) -> list[M]:
        self.session.add_all(objs)
        self.session.flush()
        return [*objs]

    def delete(self, obj: M) -> None:
        self.session.delete(obj)
        self.session.flush()


def _like(q: str) -> str:
    return f"%{q.strip()}%"
