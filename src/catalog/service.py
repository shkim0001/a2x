"""카탈로그 규칙: 자산(API · MCP) 등록 · 수정 · 진행상태 · 노출 범위.

규칙은 모두 Python 코드로 판정한다.
- 자산 관리는 소유 시스템의 담당자 또는 admin
- 진행상태: 저장 → (제출) 승인 대기 → (admin 승인) 스테이지 → (admin 운영 전환) 운영. 반려되면 수정 후 재제출
- 저장 · 반려 상태에서만 수정 가능, 저장 · 반려 자산은 소유 시스템 담당자와 admin에게만 보인다"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from src.audit.repository import AuditRepository
from src.auth.models import User
from src.catalog.models import ApiLayoutField, ApiOperation, Asset, AssetSource, AssetStatus, AssetType, IconKind, LayoutDirection, McpTool
from src.catalog.repository import AssetRepository
from src.catalog.schemas import ApiAssetIn, IconIn, McpAssetIn
from src.shared.errors import Conflict, Invalid, NotFound
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest
from src.subscriptions.repository import SubscriptionRepository
from src.systems.access import can_manage_system, ensure_admin, ensure_can_manage
from src.systems.models import System, SystemKind
from src.systems.service import get_system


# 승인 이후(스테이지 · 운영 · 중지) 수정하면 다시 승인 대기로 돌아간다(재승인)
REAPPROVE = {AssetStatus.STAGE, AssetStatus.LIVE, AssetStatus.SUSPENDED}
HIDDEN_FROM_OTHERS = {AssetStatus.DRAFT, AssetStatus.REJECTED}


# 허용되는 진행상태 전이: (현재, 동작) → 다음
TRANSITIONS: dict[tuple[AssetStatus, str], AssetStatus] = {
    (AssetStatus.DRAFT, "submit"): AssetStatus.PENDING,
    (AssetStatus.REJECTED, "submit"): AssetStatus.PENDING,
    (AssetStatus.PENDING, "approve"): AssetStatus.STAGE,
    (AssetStatus.PENDING, "reject"): AssetStatus.REJECTED,
    (AssetStatus.STAGE, "go_live"): AssetStatus.LIVE,
    (AssetStatus.LIVE, "suspend"): AssetStatus.SUSPENDED,
    (AssetStatus.SUSPENDED, "resume"): AssetStatus.LIVE,
    **{(s, "resubmit"): AssetStatus.PENDING for s in REAPPROVE},  # 승인 이후 수정 → 재승인
}


def _audit(db: Session, user: User, action: str, target_type: str, target_id, detail: dict | None = None) -> None:
    AuditRepository(db).record(user.id, action, target_type, target_id, detail)


def can_see(user: User, asset: Asset) -> bool:
    return asset.status not in HIDDEN_FROM_OTHERS or can_manage_system(user, asset.system)


def get_asset(db: Session, user: User, asset_id: int) -> Asset:
    a = AssetRepository(db).get(asset_id)
    if a is None or not can_see(user, a):
        raise NotFound("API · MCP를 찾을 수 없습니다.")
    return a


def catalog(db: Session, user: User, q: str | None, type_: AssetType | None, status: AssetStatus | None) -> list[Asset]:
    return [a for a in AssetRepository(db).catalog(q=q, type_=type_, status=status) if can_see(user, a)]


def subscriber_counts(db: Session, asset_ids: list[int]) -> dict[int, int]:
    if not asset_ids:
        return {}
    rows = db.execute(
        select(SystemSubscription.asset_id, func.count())
        .where(SystemSubscription.asset_id.in_(asset_ids), SystemSubscription.status == RequestStatus.APPROVED)
        .group_by(SystemSubscription.asset_id)
    )
    return {aid: n for aid, n in rows}


def _owned_system(db: Session, user: User, system_id: int) -> System:
    s = get_system(db, system_id)
    ensure_can_manage(user, s)
    if s.kind != SystemKind.BUSINESS:
        raise Invalid("API · MCP는 업무 시스템에만 등록합니다.", "agent_system")
    return s


def _ensure_name_free(db: Session, system_id: int, name: str, exclude_id: int | None = None) -> None:
    stmt = select(Asset.id).where(Asset.system_id == system_id, Asset.name == name)
    if exclude_id:
        stmt = stmt.where(Asset.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"같은 시스템에 '{name}'이(가) 이미 있습니다.", "name_taken")


def _apply_icon(a: Asset, icon: IconIn | None) -> None:
    if icon is None:
        a.icon_kind = a.icon_name = a.icon_color = None
    else:
        a.icon_kind, a.icon_name, a.icon_color = IconKind.PRESET, icon.name, icon.color


def _apply_common(a: Asset, data: ApiAssetIn | McpAssetIn) -> None:
    a.name, a.version, a.description = data.name, data.version, data.description
    b = data.business
    a.business_category, a.business_name, a.program_name, a.business_detail, a.impact = b.category, b.name, b.program, b.detail, b.impact
    a.auth_type, a.timeout_ms = data.auth_type, data.timeout_ms
    _apply_icon(a, data.icon)


def _apply_api(a: Asset, data: ApiAssetIn) -> None:
    keys = [(o.method, o.path) for o in data.operations]
    if len(keys) != len(set(keys)):
        raise Invalid("같은 메소드 · URL 패턴의 리소스가 두 번 들어 있습니다.", "duplicate_operation")
    _apply_common(a, data)
    a.direction, a.base_url, a.content_type = data.direction, data.base_url, data.content_type
    have = {(o.method, o.path): o for o in a.operations}
    removed = [o for k, o in have.items() if k not in set(keys)]
    sess = object_session(a)
    if removed and sess is not None:
        used = sess.scalars(select(McpTool.source_operation_id).where(McpTool.source_operation_id.in_([o.id for o in removed]))).all()
        if used:
            names = ", ".join(f"{o.method.value} {o.path}" for o in removed if o.id in set(used))
            raise Invalid(f"변환 MCP의 Tool이 쓰는 리소스는 뺄 수 없습니다: {names}", "operation_in_use")
    kept = []
    for o in data.operations:
        row = have.get((o.method, o.path))
        if row is None:
            row = ApiOperation(method=o.method, path=o.path)
        row.summary = o.summary
        kept.append(row)
    a.operations = kept
    _clear(a, "layout_fields")
    a.layout_fields = [
        ApiLayoutField(direction=d, seq=i, **f.model_dump())
        for d, fields in ((LayoutDirection.REQUEST, data.request_layout), (LayoutDirection.RESPONSE, data.response_layout))
        for i, f in enumerate(fields)
    ]


def _apply_mcp(a: Asset, system: System, data: McpAssetIn) -> None:
    names = [t.name for t in data.tools]
    if len(names) != len(set(names)):
        raise Invalid("같은 이름의 Tool이 두 번 들어 있습니다.", "duplicate_tool")
    if data.endpoint and not data.endpoint.startswith(("http://", "https://")):
        raise Invalid("엔드포인트는 http:// 또는 https://로 시작해야 합니다.", "invalid_endpoint")
    if data.host_server_id is not None and all(sv.id != data.host_server_id for sv in system.servers):
        raise Invalid("서버는 이 시스템의 서버 중에서 골라야 합니다.", "invalid_server")
    _apply_common(a, data)
    a.transport, a.endpoint, a.protocol_version, a.host_server_id = data.transport, data.endpoint, data.protocol_version, data.host_server_id
    have = {t.name: t for t in a.tools}
    removed = [t for n, t in have.items() if n not in set(names)]
    sess = object_session(a)
    if removed and sess is not None:
        used = sess.scalars(select(ToolRequest.tool_id).where(ToolRequest.tool_id.in_([t.id for t in removed]))).all()
        if used:
            gone = ", ".join(t.name for t in removed if t.id in set(used))
            raise Invalid(f"사용 신청 내역이 있는 Tool은 뺄 수 없습니다(비공개로 바꾸세요): {gone}", "tool_in_use")
    kept = []
    for t in data.tools:
        row = have.get(t.name) or McpTool(name=t.name)
        for k, v in t.model_dump().items():
            setattr(row, k, v)
        kept.append(row)
    a.tools = kept


def create_api(db: Session, user: User, data: ApiAssetIn) -> Asset:
    system = _owned_system(db, user, data.system_id)
    _ensure_name_free(db, system.id, data.name)
    a = Asset(system=system, type=AssetType.API, source=AssetSource.API, status=AssetStatus.DRAFT, created_by_id=user.id)
    _apply_api(a, data)
    AssetRepository(db).add(a)
    _audit(db, user, "asset.create", "asset", a.id, {"type": "API"})
    if data.submit:
        transition(db, user, a.id, "submit")
    return a


def create_mcp(db: Session, user: User, data: McpAssetIn) -> Asset:
    system = _owned_system(db, user, data.system_id)
    _ensure_name_free(db, system.id, data.name)
    a = Asset(system=system, type=AssetType.MCP, source=AssetSource.MCP_DIRECT, status=AssetStatus.DRAFT, created_by_id=user.id)
    _apply_mcp(a, system, data)
    AssetRepository(db).add(a)
    _audit(db, user, "asset.create", "asset", a.id, {"type": "MCP_DIRECT"})
    if data.submit:
        transition(db, user, a.id, "submit")
    return a


def update_asset(db: Session, user: User, asset_id: int, data: ApiAssetIn | McpAssetIn) -> Asset:
    a = get_asset(db, user, asset_id)
    ensure_can_manage(user, a.system)
    reapprove = a.status in REAPPROVE
    if data.system_id != a.system_id:
        raise Invalid("소속 시스템은 바꿀 수 없습니다.", "system_change")
    _ensure_name_free(db, a.system_id, data.name, exclude_id=a.id)
    if a.type == AssetType.API and isinstance(data, ApiAssetIn):
        _apply_api(a, data)
    elif a.source == AssetSource.MCP_DIRECT and isinstance(data, McpAssetIn):
        _apply_mcp(a, a.system, data)
    else:
        raise Invalid("자산 유형에 맞는 입력이 아닙니다.", "type_mismatch")
    db.flush()
    _audit(db, user, "asset.update", "asset", a.id, {"status": a.status.value})
    if reapprove:
        transition(db, user, a.id, "resubmit", "승인 이후 수정")
    elif data.submit and a.status != AssetStatus.PENDING:
        transition(db, user, a.id, "submit")
    return a


def delete_asset(db: Session, user: User, asset_id: int) -> None:
    """API · MCP 삭제: 승인 대기 · 승인 구독이 있거나 이 API로 만든 변환 MCP가 있으면 막는다(먼저 해지 · 삭제)."""
    a = get_asset(db, user, asset_id)
    ensure_can_manage(user, a.system)
    subs = SubscriptionRepository(db)
    active = subs.active_of(asset_id=a.id)
    if active:
        names = ", ".join(sorted({s.client_system.code for s in active}))
        raise Conflict(f"구독 {len(active)}건(승인 · 대기, 클라이언트: {names})이 있어 삭제할 수 없습니다. 먼저 해지하세요.", "asset_in_use")
    converted = [*db.scalars(select(Asset).where(Asset.converted_from_id == a.id))]
    if converted:
        raise Conflict(f"이 API로 만든 변환 MCP({', '.join(c.name for c in converted)})를 먼저 삭제하세요.", "asset_converted")
    purged = subs.purge_ended(asset_id=a.id)
    _audit(db, user, "asset.delete", "asset", a.id, {"name": a.name, "type": a.type.value, "status": a.status.value, "system": a.system.code, "ended_subscriptions": purged})
    db.delete(a)
    db.flush()


def set_icon(db: Session, user: User, asset_id: int, icon: IconIn | None) -> Asset:
    a = get_asset(db, user, asset_id)
    ensure_can_manage(user, a.system)
    _apply_icon(a, icon)
    db.flush()
    _audit(db, user, "asset.icon", "asset", a.id)
    return a


def _submit_problems(a: Asset) -> list[str]:
    """제출(승인 요청) 전에 갖춰야 할 항목."""
    p = []
    if a.type == AssetType.API:
        if not a.business_name:
            p.append("업무명")
        if not a.base_url:
            p.append("Base URL")
        if not a.operations:
            p.append("리소스 1개 이상")
    elif a.source == AssetSource.MCP_DIRECT:
        if not a.business_name:
            p.append("업무명")
        if not a.endpoint:
            p.append("엔드포인트")
        if not a.exposed_tools:
            p.append("공개 Tool 1개 이상")
    elif not a.tools:
        p.append("Tool 1개 이상")
    return p


def transition(db: Session, user: User, asset_id: int, action: str, note: str = "") -> Asset:
    a = get_asset(db, user, asset_id)
    nxt = TRANSITIONS.get((a.status, action))
    if nxt is None:
        raise Invalid(f"현재 상태({a.status.value})에서는 '{action}'을(를) 할 수 없습니다.", "invalid_transition")
    if action in ("submit", "resubmit"):
        ensure_can_manage(user, a.system)
        missing = _submit_problems(a)
        if missing:
            raise Invalid("승인 요청 전에 채워야 합니다: " + ", ".join(missing), "incomplete")
    else:
        ensure_admin(user)  # 승인 · 반려 · 운영 전환 · 중지는 admin
    before = a.status
    a.status = nxt
    db.flush()
    _audit(db, user, f"asset.{action}", "asset", a.id, {"from": before.value, "to": nxt.value, "note": note, "at": datetime.now(timezone.utc).isoformat()})
    return a


def _clear(a: Asset, *relations: str) -> None:
    """하위 항목을 바꿀 때 기존 행을 먼저 지운다(새 행과 고유 제약이 겹치지 않도록)."""
    sess = object_session(a)
    for rel in relations:
        getattr(a, rel).clear()
    if sess is not None and a.id is not None:
        sess.flush()
