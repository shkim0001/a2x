"""2단계 구독 API: 시스템 구독 · Tool 사용 신청 · 승인 · 해지 · 권한 확인."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.deps import current_user
from src.auth.models import User
from src.auth.schemas import UserBrief
from src.catalog.models import AssetType, ToolKind
from src.catalog.schemas import DecisionIn
from src.shared.db.session import get_db
from src.shared.schema import Schema
from src.subscriptions import service as svc
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest
from src.subscriptions.repository import ToolRequestRepository
from src.subscriptions.schemas import (
    AssetRef,
    ConnectionOut,
    ConnectionTool,
    PermissionOut,
    SubscriptionIn,
    SubscriptionOut,
    ToolRef,
    ToolRequestIn,
    ToolRequestOut,
    ToolRequestResult,
)
from src.systems.schemas import SystemBrief

router = APIRouter(tags=["subscriptions"])


def sub_out(user: User, s: SystemSubscription) -> SubscriptionOut:
    return SubscriptionOut(
        id=s.id, status=s.status, purpose=s.purpose,
        client_system=SystemBrief.model_validate(s.client_system), provider_system=SystemBrief.model_validate(s.asset.system),
        asset=AssetRef.model_validate(s.asset), requested_by=UserBrief.model_validate(s.requested_by) if s.requested_by else None,
        created_at=s.created_at, decided_at=s.decided_at, decision_note=s.decision_note,
        can_decide=svc.can_decide_subscription(user, s), can_cancel=svc.can_cancel_subscription(user, s),
    )


def tr_out(user: User, r: ToolRequest) -> ToolRequestOut:
    s = r.subscription
    return ToolRequestOut(
        id=r.id, status=r.status, purpose=r.purpose, user=UserBrief.model_validate(r.user), tool=ToolRef.model_validate(r.tool), subscription_id=s.id,
        client_system=SystemBrief.model_validate(s.client_system), provider_system=SystemBrief.model_validate(s.asset.system), asset=AssetRef.model_validate(s.asset),
        created_at=r.created_at, decided_at=r.decided_at, decision_note=r.decision_note,
        can_decide=svc.can_decide_tool(user, r), can_cancel=svc.can_cancel_tool(user, r),
    )


# ---------- 시스템 구독 ----------


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    scope: str = Query(default="approve", pattern="^(approve|requested|all)$"),
    status: RequestStatus | None = None,
    q: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [sub_out(user, s) for s in svc.list_subscriptions(db, user, scope, status, q)]


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def request_subscription(body: SubscriptionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.request_subscription(db, user, body.client_system_id, body.asset_id, body.purpose)
    db.commit()
    return sub_out(user, s)


@router.post("/subscriptions/{sub_id}/approve", response_model=SubscriptionOut)
def approve_subscription(sub_id: int, body: DecisionIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.decide_subscription(db, user, sub_id, True, body.note if body else "")
    db.commit()
    return sub_out(user, s)


@router.post("/subscriptions/{sub_id}/reject", response_model=SubscriptionOut)
def reject_subscription(sub_id: int, body: DecisionIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.decide_subscription(db, user, sub_id, False, body.note if body else "")
    db.commit()
    return sub_out(user, s)


@router.post("/subscriptions/{sub_id}/cancel", response_model=SubscriptionOut)
def cancel_subscription(sub_id: int, body: DecisionIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.cancel_subscription(db, user, sub_id, body.note if body else "")
    db.commit()
    return sub_out(user, s)


@router.get("/connections", response_model=list[ConnectionOut])
def list_connections(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tool 신청에 쓸 수 있는 연계(승인된 MCP 시스템 구독)와 공개 Tool, 내 신청 상태."""
    mine = {(r.subscription_id, r.tool_id): r.status for r in ToolRequestRepository(db).for_user(user.id) if r.status in svc.ACTIVE}
    return [
        ConnectionOut(
            subscription_id=s.id, client_system=SystemBrief.model_validate(s.client_system), provider_system=SystemBrief.model_validate(s.asset.system),
            asset=AssetRef.model_validate(s.asset),
            tools=[ConnectionTool(**ToolRef.model_validate(t).model_dump(), my_status=mine.get((s.id, t.id))) for t in s.asset.exposed_tools],
        )
        for s in svc.connections(db)
    ]


# ---------- Tool 사용 신청 ----------


@router.get("/tool-requests", response_model=list[ToolRequestOut])
def list_tool_requests(
    scope: str = Query(default="mine", pattern="^(mine|approve|requested|all)$"),
    status: RequestStatus | None = None,
    q: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [tr_out(user, r) for r in svc.list_tool_requests(db, user, scope, status, q)]


@router.post("/tool-requests", response_model=ToolRequestResult, status_code=201)
def request_tools(body: ToolRequestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    created, skipped = svc.request_tools(db, user, body.subscription_id, body.tools, body.purpose)
    db.commit()
    return ToolRequestResult(created=[tr_out(user, r) for r in created], skipped=skipped)


@router.post("/tool-requests/{tr_id}/approve", response_model=ToolRequestOut)
def approve_tool(tr_id: int, body: DecisionIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = svc.decide_tool_request(db, user, tr_id, True, body.note if body else "")
    db.commit()
    return tr_out(user, r)


@router.post("/tool-requests/{tr_id}/reject", response_model=ToolRequestOut)
def reject_tool(tr_id: int, body: DecisionIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = svc.decide_tool_request(db, user, tr_id, False, body.note if body else "")
    db.commit()
    return tr_out(user, r)


@router.post("/tool-requests/{tr_id}/cancel", response_model=ToolRequestOut)
def cancel_tool(tr_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = svc.cancel_tool_request(db, user, tr_id)
    db.commit()
    return tr_out(user, r)


@router.get("/permissions/check", response_model=PermissionOut)
def check_permission(subscription_id: int, tool: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """현재 사용자가 이 연계에서 이 Tool을 호출할 수 있는지(시스템 구독 + Tool 권한)."""
    allowed, reason = svc.is_tool_permitted(db, user.id, subscription_id, tool)
    return PermissionOut(allowed=allowed, reason=reason)
