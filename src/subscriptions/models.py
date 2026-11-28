"""구독 도메인 모델: 시스템 구독(1단계)과 사용자 Tool 신청(2단계)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.auth.models import User
from src.catalog.models import Asset, McpTool
from src.shared.db.base import Base, enum_type, TimestampMixin
from src.systems.models import System

from enum import StrEnum


class RequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"  # 해지


class SystemSubscription(TimestampMixin, Base):
    __tablename__ = "system_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_system_id: Mapped[int] = mapped_column(ForeignKey("systems.id", ondelete="RESTRICT"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    purpose: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[RequestStatus] = mapped_column(enum_type(RequestStatus, "subscription_status"), default=RequestStatus.PENDING, index=True)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str] = mapped_column(String(500), default="")

    client_system: Mapped[System] = relationship(lazy="joined")
    asset: Mapped[Asset] = relationship(lazy="joined")
    requested_by: Mapped[User | None] = relationship(foreign_keys=[requested_by_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])


class ToolRequest(TimestampMixin, Base):
    __tablename__ = "tool_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("system_subscriptions.id", ondelete="RESTRICT"), index=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("mcp_tools.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[RequestStatus] = mapped_column(enum_type(RequestStatus, "tool_request_status"), default=RequestStatus.PENDING, index=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str] = mapped_column(String(500), default="")

    subscription: Mapped[SystemSubscription] = relationship(lazy="joined")
    tool: Mapped[McpTool] = relationship(lazy="joined")
    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")


