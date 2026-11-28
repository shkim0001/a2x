"""모니터링 API (T2-4): 사용내역 · 트랜잭션 상세 · 호출 통계 · 요약. 조회 범위와 오류 분류는 monitoring/service.py 규칙."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.auth.deps import current_user
from src.auth.models import User
from src.monitoring import service as svc
from src.monitoring.models import CallLog
from src.monitoring.schemas import CallDetail, CallPage, CallRow, Classification, RecentError, StatRow, Summary, SystemRef
from src.shared.db.session import get_db
from src.systems.repository import SystemRepository

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _refs(db: Session) -> dict[int, Any]:
    return {s.id: s for s in SystemRepository(db).search()}


def _row(r: CallLog, systems: dict[int, Any], users: dict[int, tuple[str, str]]) -> dict[str, Any]:
    def ref(sid: int | None) -> dict[str, Any]:
        s = systems.get(sid) if sid else None
        return {"id": sid, "code": s.code if s else "-", "name": s.name if s else "-"}

    return {
        "tx_id": r.tx_id, "kind": r.kind.value, "success": r.success, "return_code": r.return_code, "name": r.name,
        "client_system": ref(r.client_system_id), "provider_system": ref(r.provider_system_id), "user": users[r.user_id][0] if r.user_id in users else None,
        "user_login": users[r.user_id][1] if r.user_id in users else None,  # 실제로 호출한 사용자의 로그인 ID
        "subscription_id": r.subscription_id, "started_at": svc.as_utc(r.started_at), "ended_at": svc.as_utc(r.ended_at), "duration_ms": r.duration_ms,
        "client_ip": r.client_ip, "protocol": r.protocol, "method": r.method, "uri": r.uri, "error_message": r.error_message,
    }


@router.get("/calls", response_model=CallPage)
def list_calls(
    kind: Literal["API", "MCP"] | None = None,
    status: Literal["success", "failed"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    days: int = Query(default=7, ge=1, le=90),
    start: datetime | None = Query(default=None, description="조회 시작 시각(시간대 없으면 KST)"),
    end: datetime | None = Query(default=None, description="조회 종료 시각(시간대 없으면 KST, 없으면 지금)"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows, total = svc.page_calls(db, user, kind=kind, status=status, q=q, days=days, page=page, size=size, start=start, end=end)
    systems, users = _refs(db), svc.user_names(db, {r.user_id for r in rows if r.user_id})
    return {"items": [_row(r, systems, users) for r in rows], "total": total, "page": page, "size": size}


@router.get("/calls/{tx_id}", response_model=CallDetail)
def call_detail(tx_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = svc.get_log(db, user, tx_id)
    ec = svc.classify(r.return_code)
    return {
        **_row(r, _refs(db), svc.user_names(db, {r.user_id} if r.user_id else set())),
        "request_headers": r.request_headers, "request_body": r.request_body, "response_body": r.response_body, "stages": r.stages or [],
        "classification": {"category": ec.category, "side": ec.side, "action": ec.action} if ec else None,
    }


@router.get("/stats", response_model=list[StatRow])
def call_stats(
    unit: Literal["daily", "monthly"] = "daily",
    start: date | None = None,
    end: date | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return svc.stats(db, user, unit, start=start, end=end)


@router.get("/summary", response_model=Summary)
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.summary(db, user)


@router.get("/instances")
async def instances(refresh: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """인스턴스 모니터링: A2X 구성요소 상태(시스템 담당자 · admin). refresh=true면 캐시 없이 다시 점검."""
    from src.monitoring import health
    from src.shared.errors import Forbidden
    from src.systems.access import effective_role

    if effective_role(db, user) == "USER":
        raise Forbidden("인스턴스 모니터링은 시스템 담당자와 admin만 볼 수 있습니다.", "instances_forbidden")
    return await health.check_all(db, use_cache=not refresh)
