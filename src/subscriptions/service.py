"""2단계 구독과 승인 (규칙은 모두 Python 코드로 판정).

1) 시스템 구독: 클라이언트 시스템 담당자가 운영(LIVE) 중인 API · MCP를 내 시스템으로 신청
   - 자기 시스템의 자산은 구독할 수 없다, 같은 연계의 승인 대기 · 승인 건이 있으면 중복 신청 불가
2) Tool 사용 신청: 승인된 MCP 시스템 구독 안에서 개인 사용자가 공개 Tool별로 신청
   - API 연계는 시스템 구독만 한다(Tool 신청 없음)
승인 · 반려: 대상(프로바이더) 시스템 담당자
해지: 시스템 구독은 프로바이더 · 클라이언트 담당자, Tool 신청은 본인 · 프로바이더 담당자.
      시스템 구독을 해지하면 그 안의 Tool 권한도 함께 해지된다.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.audit.repository import AuditRepository
from src.auth.models import User
from src.catalog.models import AssetStatus, AssetType
from src.catalog.service import get_asset
from src.shared.errors import Conflict, Forbidden, Invalid, NotFound
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest
from src.subscriptions.repository import SubscriptionRepository, ToolRequestRepository
from src.systems.access import can_manage_system, is_admin
from src.systems.models import System
from src.systems.repository import SystemRepository
from src.systems.service import get_system

ACTIVE = {RequestStatus.PENDING, RequestStatus.APPROVED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, user: User, action: str, target_type: str, target_id, detail: dict | None = None) -> None:
    AuditRepository(db).record(user.id, action, target_type, target_id, detail)


# ---------- 판정 도우미 (화면의 버튼 표시에도 쓴다) ----------
# 승인권자: 대상(프로바이더) 시스템 담당자, 그리고 admin(모든 시스템)


def can_approve_for(user: User, provider: System) -> bool:
    return is_admin(user) or provider.is_manager(user.id)


def _decided_as(user: User, provider: System) -> dict:
    """감사 기록용: 담당자가 아닌 admin이 처리했으면 표시한다."""
    return {"as_admin": True} if not provider.is_manager(user.id) else {}


def can_decide_subscription(user: User, sub: SystemSubscription) -> bool:
    return sub.status == RequestStatus.PENDING and can_approve_for(user, sub.asset.system)


def can_cancel_subscription(user: User, sub: SystemSubscription) -> bool:
    return sub.status in ACTIVE and (sub.asset.system.is_manager(user.id) or sub.client_system.is_manager(user.id) or is_admin(user))


def can_decide_tool(user: User, tr: ToolRequest) -> bool:
    return tr.status == RequestStatus.PENDING and can_approve_for(user, tr.subscription.asset.system)


def can_cancel_tool(user: User, tr: ToolRequest) -> bool:
    return tr.status in ACTIVE and (tr.user_id == user.id or tr.subscription.asset.system.is_manager(user.id) or is_admin(user))


# ---------- 1) 시스템 구독 ----------


def get_subscription(db: Session, sub_id: int) -> SystemSubscription:
    sub = SubscriptionRepository(db).get(sub_id)
    if sub is None:
        raise NotFound("시스템 구독을 찾을 수 없습니다.")
    return sub


def request_subscription(db: Session, user: User, client_system_id: int, asset_id: int, purpose: str) -> SystemSubscription:
    client = get_system(db, client_system_id)
    if not can_manage_system(user, client):
        raise Forbidden("시스템 구독은 구독할 시스템의 담당자가 신청합니다.", "not_client_manager")
    asset = get_asset(db, user, asset_id)
    if asset.status != AssetStatus.LIVE:
        raise Invalid("운영 중인 API · MCP만 구독할 수 있습니다.", "asset_not_live")
    if asset.system_id == client.id:
        raise Invalid("자기 시스템의 API · MCP는 구독할 수 없습니다.", "self_subscription")
    if not purpose.strip():
        raise Invalid("사용 목적을 입력하세요.", "purpose_required")
    repo = SubscriptionRepository(db)
    if repo.find_active(client.id, asset.id):
        raise Conflict("이미 신청했거나 구독 중입니다.", "already_subscribed")
    sub = repo.add(SystemSubscription(client_system_id=client.id, asset_id=asset.id, purpose=purpose.strip(), requested_by_id=user.id))
    _audit(db, user, "subscription.request", "subscription", sub.id, {"client": client.code, "asset_id": asset.id})
    return sub


def decide_subscription(db: Session, user: User, sub_id: int, approve: bool, note: str = "") -> SystemSubscription:
    sub = get_subscription(db, sub_id)
    if not can_approve_for(user, sub.asset.system):
        raise Forbidden("대상 시스템 담당자나 admin만 승인 · 반려할 수 있습니다.", "not_provider_manager")
    if sub.status != RequestStatus.PENDING:
        raise Invalid("승인 대기 중인 신청만 처리할 수 있습니다.", "not_pending")
    sub.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
    sub.decided_by_id, sub.decided_at, sub.decision_note = user.id, _now(), note
    db.flush()
    _audit(db, user, "subscription.approve" if approve else "subscription.reject", "subscription", sub.id, {"note": note, **_decided_as(user, sub.asset.system)})
    return sub


def cancel_subscription(db: Session, user: User, sub_id: int, note: str = "") -> SystemSubscription:
    sub = get_subscription(db, sub_id)
    if not can_cancel_subscription(user, sub):
        if sub.status not in ACTIVE:
            raise Invalid("이미 끝난 신청입니다.", "not_active")
        raise Forbidden("대상 · 구독 시스템 담당자만 해지할 수 있습니다.", "cannot_cancel")
    sub.status = RequestStatus.CANCELLED
    sub.decision_note = note
    # 연계가 끊기면 그 안의 Tool 권한도 끊긴다
    cancelled = 0
    for tr in ToolRequestRepository(db).list(ToolRequest.subscription_id == sub.id, ToolRequest.status.in_(ACTIVE)):
        tr.status = RequestStatus.CANCELLED
        tr.decision_note = "시스템 구독 해지"
        cancelled += 1
    db.flush()
    _audit(db, user, "subscription.cancel", "subscription", sub.id, {"tool_requests_cancelled": cancelled})
    return sub


def list_subscriptions(db: Session, user: User, scope: str, status: RequestStatus | None, q: str | None) -> list[SystemSubscription]:
    repo = SubscriptionRepository(db)
    managed = SystemRepository(db).managed_ids(user.id)
    if scope == "approve":
        rows = (
            repo.list(*([SystemSubscription.status == status] if status else []), order_by=SystemSubscription.id.desc())
            if is_admin(user)
            else repo.for_provider(managed, status)
        )
    elif scope == "requested":
        rows = repo.for_clients(managed, status)
    elif scope == "all":
        if not is_admin(user):
            raise Forbidden("전체 조회는 admin만 할 수 있습니다.", "admin_only")
        rows = repo.list(*( [SystemSubscription.status == status] if status else []), order_by=SystemSubscription.id.desc())
    else:
        raise Invalid("scope는 approve, requested, all 중 하나입니다.", "invalid_scope")
    if q:
        ql = q.lower()
        rows = [
            s for s in rows
            if any(ql in v.lower() for v in (s.client_system.name, s.client_system.code, s.asset.name, s.asset.system.name, s.purpose, s.requested_by.name if s.requested_by else ""))
        ]
    return rows


def connections(db: Session) -> list[SystemSubscription]:
    """Tool 신청에 쓸 수 있는 연계: 승인된 MCP 시스템 구독."""
    return [s for s in SubscriptionRepository(db).list(SystemSubscription.status == RequestStatus.APPROVED, order_by=SystemSubscription.id) if s.asset.type == AssetType.MCP]


# ---------- 2) Tool 사용 신청 ----------


def get_tool_request(db: Session, tr_id: int) -> ToolRequest:
    tr = ToolRequestRepository(db).get(tr_id)
    if tr is None:
        raise NotFound("Tool 사용 신청을 찾을 수 없습니다.")
    return tr


def request_tools(db: Session, user: User, subscription_id: int, tool_names: list[str], purpose: str) -> tuple[list[ToolRequest], list[str]]:
    """Tool 여러 개를 한 번에 신청. 이미 신청 · 사용 중인 Tool은 건너뛰고 이름을 돌려준다."""
    sub = get_subscription(db, subscription_id)
    if sub.status != RequestStatus.APPROVED:
        raise Invalid("시스템 구독이 승인된 연계에서만 Tool을 신청할 수 있습니다.", "subscription_not_approved")
    if sub.asset.type != AssetType.MCP:
        raise Invalid("API 연계는 시스템 구독만 합니다. Tool 신청은 MCP에만 있습니다.", "not_mcp")
    if not tool_names:
        raise Invalid("Tool을 하나 이상 고르세요.", "no_tools")
    if not purpose.strip():
        raise Invalid("사용 목적을 입력하세요.", "purpose_required")
    tools = {t.name: t for t in sub.asset.exposed_tools}
    unknown = [n for n in tool_names if n not in tools]
    if unknown:
        raise Invalid("공개되지 않았거나 없는 Tool입니다: " + ", ".join(unknown), "unknown_tool")
    repo = ToolRequestRepository(db)
    created, skipped = [], []
    for name in dict.fromkeys(tool_names):  # 순서 유지 중복 제거
        tool = tools[name]
        if repo.find_active(user.id, sub.id, tool.id):
            skipped.append(name)
            continue
        created.append(repo.add(ToolRequest(subscription_id=sub.id, tool_id=tool.id, user_id=user.id, purpose=purpose.strip())))
    if created:
        _audit(db, user, "tool_request.create", "subscription", sub.id, {"tools": [t.tool.name for t in created]})
    return created, skipped


def decide_tool_request(db: Session, user: User, tr_id: int, approve: bool, note: str = "") -> ToolRequest:
    tr = get_tool_request(db, tr_id)
    if not can_approve_for(user, tr.subscription.asset.system):
        raise Forbidden("대상 시스템 담당자나 admin만 승인 · 반려할 수 있습니다.", "not_provider_manager")
    if tr.status != RequestStatus.PENDING:
        raise Invalid("승인 대기 중인 신청만 처리할 수 있습니다.", "not_pending")
    if approve and tr.subscription.status != RequestStatus.APPROVED:
        raise Invalid("시스템 구독이 해지된 연계입니다.", "subscription_not_approved")
    tr.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
    tr.decided_by_id, tr.decided_at, tr.decision_note = user.id, _now(), note
    db.flush()
    _audit(db, user, "tool_request.approve" if approve else "tool_request.reject", "tool_request", tr.id, {"note": note, **_decided_as(user, tr.subscription.asset.system)})
    return tr


def cancel_tool_request(db: Session, user: User, tr_id: int) -> ToolRequest:
    tr = get_tool_request(db, tr_id)
    if not can_cancel_tool(user, tr):
        if tr.status not in ACTIVE:
            raise Invalid("이미 끝난 신청입니다.", "not_active")
        raise Forbidden("본인 또는 대상 시스템 담당자만 해지할 수 있습니다.", "cannot_cancel")
    tr.status = RequestStatus.CANCELLED
    db.flush()
    _audit(db, user, "tool_request.cancel", "tool_request", tr.id)
    return tr


def list_tool_requests(db: Session, user: User, scope: str, status: RequestStatus | None, q: str | None) -> list[ToolRequest]:
    repo = ToolRequestRepository(db)
    if scope == "mine":
        rows = repo.for_user(user.id)
        if status:
            rows = [r for r in rows if r.status == status]
    elif scope == "approve":
        rows = (
            repo.list(*([ToolRequest.status == status] if status else []), order_by=ToolRequest.id.desc())
            if is_admin(user)
            else repo.for_provider(SystemRepository(db).managed_ids(user.id), status)
        )
    elif scope == "requested":
        # 내 시스템(클라이언트 Agent)의 연계에서 들어간 신청
        managed = SystemRepository(db).managed_ids(user.id)
        rows = [r for r in repo.list(order_by=ToolRequest.id.desc()) if r.subscription.client_system_id in managed and (not status or r.status == status)]
    elif scope == "all":
        if not is_admin(user):
            raise Forbidden("전체 조회는 admin만 할 수 있습니다.", "admin_only")
        rows = repo.list(*([ToolRequest.status == status] if status else []), order_by=ToolRequest.id.desc())
    else:
        raise Invalid("scope는 mine, approve, requested, all 중 하나입니다.", "invalid_scope")
    if q:
        ql = q.lower()
        rows = [r for r in rows if any(ql in v.lower() for v in (r.user.name, r.tool.name, r.purpose, r.subscription.client_system.name, r.subscription.asset.name))]
    return rows


def is_tool_permitted(db: Session, user_id: int, subscription_id: int, tool_name: str) -> tuple[bool, str]:
    """호출 시점 판정(Gateway · 컨버터가 쓴다): 시스템 구독 승인 + 사용자 Tool 권한 승인."""
    sub = SubscriptionRepository(db).get(subscription_id)
    if sub is None or sub.status != RequestStatus.APPROVED:
        return False, "시스템 구독이 승인되지 않은 연계입니다."
    if sub.asset.status != AssetStatus.LIVE:
        return False, "운영 중이 아닌 MCP 서버입니다."
    tool = next((t for t in sub.asset.exposed_tools if t.name == tool_name), None)
    if tool is None:
        return False, f"공개되지 않았거나 없는 Tool입니다: {tool_name}"
    if not ToolRequestRepository(db).is_permitted(user_id, sub.id, tool.id):
        return False, f"사용자에게 {tool_name} 사용 권한이 없습니다."
    return True, "허용"
