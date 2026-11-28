"""구독 도메인 저장소."""

from __future__ import annotations

from sqlalchemy import select

from src.catalog.models import Asset
from src.shared.db.repository import Repository
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest


ACTIVE = (RequestStatus.PENDING, RequestStatus.APPROVED)


class SubscriptionRepository(Repository[SystemSubscription]):
    model = SystemSubscription

    def _of(self, asset_id: int | None, client_system_id: int | None):
        stmt = select(SystemSubscription)
        if asset_id is not None:
            stmt = stmt.where(SystemSubscription.asset_id == asset_id)
        if client_system_id is not None:
            stmt = stmt.where(SystemSubscription.client_system_id == client_system_id)
        return stmt

    def active_of(self, *, asset_id: int | None = None, client_system_id: int | None = None) -> list[SystemSubscription]:
        """자산 · 클라이언트 시스템의 승인 대기 · 승인 구독(삭제를 막는 연결)."""
        return [*self.session.scalars(self._of(asset_id, client_system_id).where(SystemSubscription.status.in_(ACTIVE))).unique()]

    def purge_ended(self, *, asset_id: int | None = None, client_system_id: int | None = None) -> int:
        """끝난(반려 · 해지) 구독과 그 Tool 신청 이력을 지운다. 자산 · 시스템 삭제 때만 쓴다(감사 로그 · 호출 로그는 남음)."""
        subs = [*self.session.scalars(self._of(asset_id, client_system_id).where(SystemSubscription.status.not_in(ACTIVE))).unique()]
        for sub in subs:
            for tr in self.session.scalars(select(ToolRequest).where(ToolRequest.subscription_id == sub.id)).unique():
                self.session.delete(tr)
        self.session.flush()
        for sub in subs:
            self.session.delete(sub)
        self.session.flush()
        return len(subs)

    def find_active(self, client_system_id: int, asset_id: int) -> SystemSubscription | None:
        """같은 클라이언트 → 같은 자산의 승인 대기 · 승인 건(중복 신청 방지용)."""
        return self.session.scalar(
            select(SystemSubscription).where(
                SystemSubscription.client_system_id == client_system_id,
                SystemSubscription.asset_id == asset_id,
                SystemSubscription.status.in_(ACTIVE),
            )
        )

    def for_provider(self, provider_system_ids: set[int], status: RequestStatus | None = None) -> list[SystemSubscription]:
        stmt = select(SystemSubscription).join(Asset, SystemSubscription.asset_id == Asset.id).where(Asset.system_id.in_(provider_system_ids))
        if status:
            stmt = stmt.where(SystemSubscription.status == status)
        return [*self.session.scalars(stmt.order_by(SystemSubscription.id.desc())).unique()]

    def for_clients(self, client_system_ids: set[int], status: RequestStatus | None = None) -> list[SystemSubscription]:
        stmt = select(SystemSubscription).where(SystemSubscription.client_system_id.in_(client_system_ids))
        if status:
            stmt = stmt.where(SystemSubscription.status == status)
        return [*self.session.scalars(stmt.order_by(SystemSubscription.id.desc())).unique()]


class ToolRequestRepository(Repository[ToolRequest]):
    model = ToolRequest

    def find_active(self, user_id: int, subscription_id: int, tool_id: int) -> ToolRequest | None:
        return self.session.scalar(
            select(ToolRequest).where(
                ToolRequest.user_id == user_id,
                ToolRequest.subscription_id == subscription_id,
                ToolRequest.tool_id == tool_id,
                ToolRequest.status.in_(ACTIVE),
            )
        )

    def for_user(self, user_id: int) -> list[ToolRequest]:
        return self.list(ToolRequest.user_id == user_id, order_by=ToolRequest.id.desc())

    def for_provider(self, provider_system_ids: set[int], status: RequestStatus | None = None) -> list[ToolRequest]:
        stmt = (
            select(ToolRequest)
            .join(SystemSubscription, ToolRequest.subscription_id == SystemSubscription.id)
            .join(Asset, SystemSubscription.asset_id == Asset.id)
            .where(Asset.system_id.in_(provider_system_ids))
        )
        if status:
            stmt = stmt.where(ToolRequest.status == status)
        return [*self.session.scalars(stmt.order_by(ToolRequest.id.desc())).unique()]

    def is_permitted(self, user_id: int, subscription_id: int, tool_id: int) -> bool:
        """호출 시점 판정: 이 사용자가 이 연계의 이 Tool을 승인받았는가."""
        return (
            self.session.scalar(
                select(ToolRequest.id).where(
                    ToolRequest.user_id == user_id,
                    ToolRequest.subscription_id == subscription_id,
                    ToolRequest.tool_id == tool_id,
                    ToolRequest.status == RequestStatus.APPROVED,
                )
            )
            is not None
        )
