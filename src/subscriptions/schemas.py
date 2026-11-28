"""구독 도메인 입출력 스키마(시스템 구독 · Tool 신청 · 권한 확인)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.auth.schemas import UserBrief
from src.catalog.models import AssetType, ToolKind
from src.shared.schema import Schema
from src.subscriptions.models import RequestStatus
from src.systems.schemas import SystemBrief


class AssetRef(Schema):
    id: int
    name: str
    type: AssetType


class SubscriptionIn(BaseModel):
    client_system_id: int
    asset_id: int
    purpose: str = Field(max_length=1000)


class SubscriptionOut(Schema):
    id: int
    status: RequestStatus
    purpose: str
    client_system: SystemBrief
    provider_system: SystemBrief
    asset: AssetRef
    requested_by: UserBrief | None
    created_at: datetime | None
    decided_at: datetime | None
    decision_note: str
    can_decide: bool
    can_cancel: bool


class ToolRef(Schema):
    id: int
    name: str
    kind: ToolKind
    description: str


class ToolRequestIn(BaseModel):
    subscription_id: int
    tools: list[str] = Field(min_length=1, max_length=50)
    purpose: str = Field(max_length=1000)


class ToolRequestOut(Schema):
    id: int
    status: RequestStatus
    purpose: str
    user: UserBrief
    tool: ToolRef
    subscription_id: int
    client_system: SystemBrief
    provider_system: SystemBrief
    asset: AssetRef
    created_at: datetime | None
    decided_at: datetime | None
    decision_note: str
    can_decide: bool
    can_cancel: bool


class ToolRequestResult(BaseModel):
    created: list[ToolRequestOut]
    skipped: list[str]  # 이미 신청 · 사용 중이라 건너뛴 Tool


class ConnectionTool(ToolRef):
    my_status: RequestStatus | None  # 내 신청 상태(없으면 null)


class ConnectionOut(Schema):
    subscription_id: int
    client_system: SystemBrief
    provider_system: SystemBrief
    asset: AssetRef
    tools: list[ConnectionTool]


class PermissionOut(BaseModel):
    allowed: bool
    reason: str
