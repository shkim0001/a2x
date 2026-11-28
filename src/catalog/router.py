"""카탈로그(API · MCP 자산 조회 · 등록 · 진행상태) API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.shared.schema import Message
from src.auth.deps import current_user
from src.auth.models import User
from src.catalog import service as svc
from src.catalog.models import Asset, AssetStatus, AssetType, LayoutDirection
from src.catalog.schemas import (
    ApiAssetIn,
    AssetDetail,
    AssetSummary,
    BusinessIn,
    DecisionIn,
    IconIn,
    IconOut,
    LayoutFieldOut,
    McpAssetIn,
    OperationOut,
    ToolOut,
)
from src.shared.db.session import get_db
from src.systems.schemas import SystemBrief


router = APIRouter(tags=["catalog"])


def _icon(a: Asset) -> IconOut | None:
    return IconOut(kind=a.icon_kind.value, name=a.icon_name, color=a.icon_color) if a.icon_kind else None


def asset_summary(a: Asset, subscribers: int = 0) -> AssetSummary:
    return AssetSummary(
        id=a.id, type=a.type, source=a.source, status=a.status, name=a.name, version=a.version, description=a.description,
        system=SystemBrief.model_validate(a.system), icon=_icon(a),
        operation_count=len(a.operations), tool_count=len(a.exposed_tools), subscriber_count=subscribers,
        converted_from_id=a.converted_from_id, updated_at=a.updated_at,
    )


def asset_detail(a: Asset, subscribers: int = 0) -> AssetDetail:
    layout = [LayoutFieldOut(direction=f.direction.value, seq=f.seq, name=f.name, type=f.type, required=f.required, description=f.description) for f in a.layout_fields]
    return AssetDetail(
        **asset_summary(a, subscribers).model_dump(),
        business=BusinessIn(category=a.business_category, name=a.business_name, program=a.program_name, detail=a.business_detail, impact=a.impact),
        direction=a.direction, base_url=a.base_url, auth_type=a.auth_type, content_type=a.content_type, timeout_ms=a.timeout_ms,
        operations=[OperationOut.model_validate(o) for o in a.operations],
        request_layout=[f for f in layout if f.direction == LayoutDirection.REQUEST.value],
        response_layout=[f for f in layout if f.direction == LayoutDirection.RESPONSE.value],
        transport=a.transport, endpoint=a.endpoint, protocol_version=a.protocol_version, host_server_id=a.host_server_id,
        tools=[ToolOut.model_validate(t) for t in a.tools],
    )


def _detail(db: Session, a: Asset) -> AssetDetail:
    return asset_detail(a, svc.subscriber_counts(db, [a.id]).get(a.id, 0))


@router.get("/assets", response_model=list[AssetSummary])
def catalog(
    q: str | None = None,
    type: AssetType | None = Query(default=None),
    status: AssetStatus | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    assets = svc.catalog(db, user, q, type, status)
    counts = svc.subscriber_counts(db, [a.id for a in assets])
    return [asset_summary(a, counts.get(a.id, 0)) for a in assets]


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def get_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _detail(db, svc.get_asset(db, user, asset_id))


@router.post("/assets/api", response_model=AssetDetail, status_code=201)
def create_api(body: ApiAssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = svc.create_api(db, user, body)
    db.commit()
    return _detail(db, a)


@router.post("/assets/mcp", response_model=AssetDetail, status_code=201)
def create_mcp(body: McpAssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = svc.create_mcp(db, user, body)
    db.commit()
    return _detail(db, a)


@router.put("/assets/{asset_id}/api", response_model=AssetDetail)
def update_api(asset_id: int, body: ApiAssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = svc.update_asset(db, user, asset_id, body)
    db.commit()
    return _detail(db, a)


@router.put("/assets/{asset_id}/mcp", response_model=AssetDetail)
def update_mcp(asset_id: int, body: McpAssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = svc.update_asset(db, user, asset_id, body)
    db.commit()
    return _detail(db, a)


@router.delete("/assets/{asset_id}", response_model=Message)
def delete_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.delete_asset(db, user, asset_id)
    db.commit()
    return Message(message="삭제했습니다.")


@router.put("/assets/{asset_id}/icon", response_model=AssetDetail)
def set_icon(asset_id: int, body: IconIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = svc.set_icon(db, user, asset_id, body)
    db.commit()
    return _detail(db, a)


def _transition(action: str):
    def handler(asset_id: int, body: DecisionIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
        a = svc.transition(db, user, asset_id, action, body.note if body else "")
        db.commit()
        return _detail(db, a)

    return handler


# 제출(담당자) · 승인 · 반려 · 운영 전환 · 중지 · 재개(admin)
for _path, _action in [("submit", "submit"), ("approve", "approve"), ("reject", "reject"), ("go-live", "go_live"), ("suspend", "suspend"), ("resume", "resume")]:
    router.add_api_route(f"/assets/{{asset_id}}/{_path}", _transition(_action), methods=["POST"], response_model=AssetDetail, name=f"asset_{_action}")
