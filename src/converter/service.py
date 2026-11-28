"""API → MCP 변환 (T2-6). 변환된 MCP 서버는 컨버터 런타임(T2-7)이 실행한다.

규칙(코드 판정):
- 원본은 운영(LIVE) 중인 API, 변환은 원본 시스템 담당자 또는 admin
- 고른 오퍼레이션은 원본 API의 것이어야 하고, Tool 이름은 형식에 맞고 겹치지 않아야 한다
- 만든 MCP 서버는 원본 시스템 소속, 진행상태는 다른 자산과 같다(제출 → admin 승인)
"""

from sqlalchemy.orm import Session

from src.audit.repository import AuditRepository
from src.auth.models import User
from src.catalog.models import Asset, AssetSource, AssetStatus, AssetType, IconKind, McpTool, McpTransport
from src.catalog.repository import AssetRepository
from src.catalog.service import _ensure_name_free, get_asset, transition
from src.converter.naming import default_description, suggest, tool_kind, TOOL_NAME_RE
from src.shared.config import settings
from src.shared.errors import Invalid
from src.systems.access import ensure_can_manage


def _source_api(db: Session, user: User, api_id: int) -> Asset:
    api = get_asset(db, user, api_id)
    if api.type != AssetType.API:
        raise Invalid("API만 MCP로 변환할 수 있습니다.", "not_api")
    ensure_can_manage(user, api.system)
    if api.status != AssetStatus.LIVE:
        raise Invalid("운영 중인 API만 변환할 수 있습니다.", "api_not_live")
    return api


def preview(db: Session, user: User, api_id: int) -> list[dict]:
    api = _source_api(db, user, api_id)
    return [suggest(op, api.layout_fields) for op in api.operations]


def convert(db: Session, user: User, api_id: int, name: str, description: str, tools: list[dict], submit: bool = False) -> Asset:
    """tools: [{operation_id, name?, description?}] — 이름 · 설명을 비우면 규칙 기본값."""
    api = _source_api(db, user, api_id)
    if not tools:
        raise Invalid("Tool로 만들 오퍼레이션을 하나 이상 고르세요.", "no_tools")
    ops = {op.id: op for op in api.operations}
    built: list[McpTool] = []
    for t in tools:
        op = ops.get(t["operation_id"])
        if op is None:
            raise Invalid(f"이 API의 오퍼레이션이 아닙니다: {t['operation_id']}", "unknown_operation")
        tname = (t.get("name") or suggest(op)["tool_name"]).strip()
        if not TOOL_NAME_RE.match(tname):
            raise Invalid(f"Tool 이름 형식이 맞지 않습니다: {tname}", "invalid_tool_name")
        built.append(McpTool(name=tname, description=(t.get("description") or default_description(op)).strip(), kind=tool_kind(op.method), source_operation_id=op.id))
    names = [b.name for b in built]
    if len(names) != len(set(names)):
        raise Invalid("Tool 이름이 겹칩니다.", "duplicate_tool")
    _ensure_name_free(db, api.system_id, name)

    mcp = Asset(
        system_id=api.system_id, type=AssetType.MCP, source=AssetSource.MCP_CONVERTED, status=AssetStatus.DRAFT,
        name=name, description=description or f"{api.name}를 MCP Tool로 변환해 제공", created_by_id=user.id,
        converted_from_id=api.id, transport=McpTransport.STREAMABLE_HTTP, protocol_version="2025-06-18",
        business_category=api.business_category, business_name=api.business_name, impact=api.impact,
        # 원본 API의 대표 이미지를 물려받는다
        icon_kind=api.icon_kind, icon_name=api.icon_name, icon_color=api.icon_color if api.icon_kind != IconKind.PRESET else "#6e4ff6",
    )
    mcp.tools = built
    AssetRepository(db).add(mcp)
    mcp.endpoint = f"{settings.CONVERTER_PUBLIC_URL.rstrip('/')}/mcp/{mcp.id}"
    db.flush()
    AuditRepository(db).record(user.id, "asset.convert", "asset", mcp.id, {"from_api": api.id, "tools": names})
    if submit:
        transition(db, user, mcp.id, "submit")
    return mcp
