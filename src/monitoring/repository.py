"""모니터링 도메인 저장소."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select

from src.monitoring.models import CallLog
from src.shared.db.repository import Repository


class CallLogRepository(Repository[CallLog]):
    model = CallLog

    def get_by_tx(self, tx_id: str) -> CallLog | None:
        return self.session.scalar(select(CallLog).where(CallLog.tx_id == tx_id))

    def _filtered(
        self,
        scope: tuple[set[int], int] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        failed_only: bool = False,
        success_only: bool = False,
        kind: Any = None,
        system_ids: set[int] | None = None,
        codes: set[str] | None = None,
        subscription_id: int | None = None,
        text: tuple[str, set[int], set[int]] | None = None,
    ):
        """조회 조건. scope: None이면 전체, (시스템 ID들, 사용자 ID)면 그 시스템이 클라이언트 · 프로바이더이거나 그 사용자의 호출.
        text: (검색어, 이름이 맞는 시스템 ID들, 이름이 맞는 사용자 ID들) — 트랜잭션 ID · 이름 · URI · 코드 · 오류 메시지 · 시스템 · 사용자."""
        conds = []
        if scope is not None:
            ids, uid = scope
            conds.append(or_(CallLog.client_system_id.in_(ids), CallLog.provider_system_id.in_(ids), CallLog.user_id == uid))
        if since:
            conds.append(CallLog.started_at >= since)
        if until:
            conds.append(CallLog.started_at < until)
        if failed_only:
            conds.append(CallLog.success.is_(False))
        if success_only:
            conds.append(CallLog.success.is_(True))
        if kind:
            conds.append(CallLog.kind == kind)
        if system_ids:
            conds.append(or_(CallLog.client_system_id.in_(system_ids), CallLog.provider_system_id.in_(system_ids)))
        if codes:
            conds.append(CallLog.return_code.in_(codes))
        if subscription_id:
            conds.append(CallLog.subscription_id == subscription_id)
        if text:
            q, sys_ids, user_ids = text
            like = f"%{q}%"
            conds.append(or_(
                CallLog.tx_id.ilike(like), CallLog.name.ilike(like), CallLog.uri.ilike(like), CallLog.return_code.ilike(like), CallLog.error_message.ilike(like),
                CallLog.client_system_id.in_(sys_ids), CallLog.provider_system_id.in_(sys_ids), CallLog.user_id.in_(user_ids),
            ))
        return conds

    def search(self, limit: int | None = 5000, offset: int = 0, **filters: Any) -> list[CallLog]:
        """최신순 조회(필터는 _filtered와 같다)."""
        stmt = select(CallLog).where(*self._filtered(**filters)).order_by(CallLog.started_at.desc(), CallLog.id.desc())
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        return [*self.session.scalars(stmt)]

    def count_filtered(self, **filters: Any) -> int:
        return self.session.scalar(select(func.count()).select_from(CallLog).where(*self._filtered(**filters))) or 0
