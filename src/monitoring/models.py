"""모니터링 도메인 모델: API · MCP 호출 트랜잭션 로그."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base, enum_type

from enum import StrEnum


class CallKind(StrEnum):
    API = "API"
    MCP = "MCP"


class CallLog(Base):
    """API · MCP 호출 트랜잭션. 1차는 샘플 생성기, 3차 Gateway 연동 시 실제 로그."""

    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tx_id: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[CallKind] = mapped_column(enum_type(CallKind, "call_kind"), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    return_code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(250))  # 호출 시점의 API · Tool 이름(스냅샷)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), index=True)
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("mcp_tools.id", ondelete="SET NULL"))
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("system_subscriptions.id", ondelete="SET NULL"))
    client_system_id: Mapped[int | None] = mapped_column(ForeignKey("systems.id", ondelete="SET NULL"), index=True)
    provider_system_id: Mapped[int | None] = mapped_column(ForeignKey("systems.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    client_ip: Mapped[str] = mapped_column(String(45), default="")
    protocol: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(20))
    uri: Mapped[str] = mapped_column(String(1000))
    error_message: Mapped[str] = mapped_column(String(500), default="")
    # 상세(인증 정보 · 개인정보는 마스킹해서 저장)
    request_headers: Mapped[dict | None] = mapped_column(JSON)
    request_body: Mapped[dict | list | None] = mapped_column(JSON)
    response_body: Mapped[dict | list | None] = mapped_column(JSON)
    stages: Mapped[list | None] = mapped_column(JSON)  # [{name, ms, ok}]


