"""카탈로그 도메인 모델: API · MCP 자산과 오퍼레이션 · 레이아웃 · Tool, 진행상태 등 코드값."""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.db.base import Base, enum_type, TimestampMixin
from src.systems.models import Server, System

from enum import StrEnum


class AssetType(StrEnum):
    API = "API"
    MCP = "MCP"


class AssetSource(StrEnum):
    API = "API"  # 등록한 API
    MCP_DIRECT = "MCP_DIRECT"  # 타겟 시스템이 직접 개발한 MCP 서버
    MCP_CONVERTED = "MCP_CONVERTED"  # A2X가 API를 변환해 만든 MCP 서버


class AssetStatus(StrEnum):
    DRAFT = "DRAFT"  # 저장
    PENDING = "PENDING"  # 승인 대기
    STAGE = "STAGE"  # 스테이지
    LIVE = "LIVE"  # 운영
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class Impact(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DataDirection(StrEnum):
    SEND = "SEND"  # 송신(이 시스템이 제공)
    RECEIVE = "RECEIVE"  # 수신


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class LayoutDirection(StrEnum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"


class ToolKind(StrEnum):
    READ = "READ"  # 조회
    WRITE = "WRITE"  # 변경


class McpTransport(StrEnum):
    STREAMABLE_HTTP = "STREAMABLE_HTTP"
    SSE = "SSE"


class IconKind(StrEnum):
    PRESET = "PRESET"
    IMAGE = "IMAGE"


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("system_id", "name"),
        # 유형과 출처가 맞아야 한다: API는 API, MCP는 직접 개발 또는 변환
        CheckConstraint(
            "(type = 'API' AND source = 'API') OR (type = 'MCP' AND source IN ('MCP_DIRECT', 'MCP_CONVERTED'))",
            name="type_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id", ondelete="RESTRICT"), index=True)
    type: Mapped[AssetType] = mapped_column(enum_type(AssetType, "asset_type"))
    source: Mapped[AssetSource] = mapped_column(enum_type(AssetSource, "asset_source"))
    status: Mapped[AssetStatus] = mapped_column(enum_type(AssetStatus, "asset_status"), default=AssetStatus.DRAFT, index=True)
    name: Mapped[str] = mapped_column(String(150))
    version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    description: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # 카탈로그 대표 이미지
    icon_kind: Mapped[IconKind | None] = mapped_column(enum_type(IconKind, "icon_kind"))
    icon_name: Mapped[str | None] = mapped_column(String(30))
    icon_color: Mapped[str | None] = mapped_column(String(9))
    icon_image_path: Mapped[str | None] = mapped_column(String(500))

    # 업무정보
    business_category: Mapped[str] = mapped_column(String(30), default="")
    business_name: Mapped[str] = mapped_column(String(100), default="")
    program_name: Mapped[str] = mapped_column(String(100), default="")
    business_detail: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[Impact] = mapped_column(enum_type(Impact, "impact"), default=Impact.MEDIUM)

    # API 정보
    direction: Mapped[DataDirection | None] = mapped_column(enum_type(DataDirection, "data_direction"))
    base_url: Mapped[str | None] = mapped_column(String(500))
    auth_type: Mapped[str | None] = mapped_column(String(50))
    content_type: Mapped[str | None] = mapped_column(String(100))
    timeout_ms: Mapped[int | None] = mapped_column(Integer)

    # MCP 정보 (직접 개발한 MCP 서버)
    transport: Mapped[McpTransport | None] = mapped_column(enum_type(McpTransport, "mcp_transport"))
    endpoint: Mapped[str | None] = mapped_column(String(500))
    protocol_version: Mapped[str | None] = mapped_column(String(20))
    host_server_id: Mapped[int | None] = mapped_column(ForeignKey("servers.id", ondelete="SET NULL"))

    # MCP 정보 (변환으로 만든 MCP 서버의 원본 API)
    converted_from_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), index=True)

    system: Mapped[System] = relationship(lazy="joined")
    host_server: Mapped[Server | None] = relationship()
    converted_from: Mapped["Asset | None"] = relationship(remote_side="Asset.id")
    operations: Mapped[list["ApiOperation"]] = relationship(back_populates="asset", cascade="all, delete-orphan", lazy="selectin", order_by="ApiOperation.id")
    layout_fields: Mapped[list["ApiLayoutField"]] = relationship(back_populates="asset", cascade="all, delete-orphan", order_by="ApiLayoutField.seq")
    tools: Mapped[list["McpTool"]] = relationship(back_populates="asset", cascade="all, delete-orphan", lazy="selectin", order_by="McpTool.id")

    @property
    def exposed_tools(self) -> list["McpTool"]:
        return [t for t in self.tools if t.exposed]


class ApiOperation(Base):
    """API 리소스(HTTP 메소드 + URL 패턴). API → MCP 변환 시 Tool 하나가 된다."""

    __tablename__ = "api_operations"
    __table_args__ = (UniqueConstraint("asset_id", "method", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    method: Mapped[HttpMethod] = mapped_column(enum_type(HttpMethod, "http_method"))
    path: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(String(300), default="")

    asset: Mapped[Asset] = relationship(back_populates="operations")


class ApiLayoutField(Base):
    __tablename__ = "api_layout_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    direction: Mapped[LayoutDirection] = mapped_column(enum_type(LayoutDirection, "layout_direction"))
    seq: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20), default="string")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(500), default="")

    asset: Mapped[Asset] = relationship(back_populates="layout_fields")


class McpTool(Base):
    __tablename__ = "mcp_tools"
    __table_args__ = (UniqueConstraint("asset_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[ToolKind] = mapped_column(enum_type(ToolKind, "tool_kind"), default=ToolKind.READ)
    exposed: Mapped[bool] = mapped_column(Boolean, default=True)  # 카탈로그 공개 여부
    # 변환으로 만든 Tool의 원본 오퍼레이션
    source_operation_id: Mapped[int | None] = mapped_column(ForeignKey("api_operations.id", ondelete="SET NULL"))

    asset: Mapped[Asset] = relationship(back_populates="tools")
    source_operation: Mapped[ApiOperation | None] = relationship()


