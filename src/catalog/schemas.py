"""카탈로그(API · MCP 등록 · 조회) 입출력 스키마."""

from datetime import datetime

from pydantic import BaseModel, Field

from src.catalog.models import AssetSource, AssetStatus, AssetType, DataDirection, HttpMethod, Impact, McpTransport, ToolKind
from src.shared.schema import Schema
from src.systems.schemas import SystemBrief


class IconIn(BaseModel):
    """준비된 아이콘 + 색. (이미지 올리기는 파일 저장소가 정해지면 추가)"""

    name: str = Field(min_length=1, max_length=30, pattern=r"^[a-z]+$")
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class BusinessIn(BaseModel):
    category: str = Field(default="", max_length=30)
    name: str = Field(default="", max_length=100)
    program: str = Field(default="", max_length=100)
    detail: str = ""
    impact: Impact = Impact.MEDIUM


class OperationIn(BaseModel):
    method: HttpMethod
    path: str = Field(min_length=1, max_length=300, pattern=r"^/")
    summary: str = Field(default="", max_length=300)


class LayoutFieldIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(default="string", pattern=r"^(string|integer|number|boolean|object|array|null)$")
    required: bool = False
    description: str = Field(default="", max_length=500)


class ToolIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = ""
    kind: ToolKind = ToolKind.READ
    exposed: bool = True


class ApiAssetIn(BaseModel):
    system_id: int
    name: str = Field(min_length=1, max_length=150)
    version: str = Field(default="1.0.0", max_length=30)
    description: str = ""
    icon: IconIn | None = None
    business: BusinessIn = BusinessIn()
    direction: DataDirection = DataDirection.SEND
    base_url: str = Field(default="", max_length=500)
    auth_type: str = Field(default="", max_length=50)
    content_type: str = Field(default="application/json", max_length=100)
    timeout_ms: int = Field(default=5000, ge=100, le=600000)
    operations: list[OperationIn] = []
    request_layout: list[LayoutFieldIn] = []
    response_layout: list[LayoutFieldIn] = []
    submit: bool = False  # True면 저장과 함께 승인 요청


class McpAssetIn(BaseModel):
    system_id: int
    name: str = Field(min_length=1, max_length=150)
    version: str = Field(default="1.0.0", max_length=30)
    description: str = ""
    icon: IconIn | None = None
    business: BusinessIn = BusinessIn()
    transport: McpTransport = McpTransport.STREAMABLE_HTTP
    endpoint: str = Field(default="", max_length=500)
    auth_type: str = Field(default="", max_length=50)
    host_server_id: int | None = None
    protocol_version: str = Field(default="2025-06-18", max_length=20)
    timeout_ms: int = Field(default=10000, ge=100, le=600000)
    tools: list[ToolIn] = []
    submit: bool = False


class DecisionIn(BaseModel):
    note: str = Field(default="", max_length=500)


class IconOut(Schema):
    kind: str
    name: str | None
    color: str | None


class OperationOut(Schema):
    id: int
    method: HttpMethod
    path: str
    summary: str


class LayoutFieldOut(Schema):
    direction: str
    seq: int
    name: str
    type: str
    required: bool
    description: str


class ToolOut(Schema):
    id: int
    name: str
    description: str
    kind: ToolKind
    exposed: bool
    source_operation_id: int | None


class AssetSummary(Schema):
    id: int
    type: AssetType
    source: AssetSource
    status: AssetStatus
    name: str
    version: str
    description: str
    system: SystemBrief
    icon: IconOut | None
    operation_count: int
    tool_count: int
    subscriber_count: int
    converted_from_id: int | None
    updated_at: datetime | None


class AssetDetail(AssetSummary):
    business: BusinessIn
    # API
    direction: DataDirection | None
    base_url: str | None
    auth_type: str | None
    content_type: str | None
    timeout_ms: int | None
    operations: list[OperationOut]
    request_layout: list[LayoutFieldOut]
    response_layout: list[LayoutFieldOut]
    # MCP
    transport: McpTransport | None
    endpoint: str | None
    protocol_version: str | None
    host_server_id: int | None
    tools: list[ToolOut]
