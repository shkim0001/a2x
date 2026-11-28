"""포탈 내부 Tool (읽기 전용). 로그인 사용자로 서비스 · 저장소 함수를 불러 화면과 같은 권한 판정을 따른다(가드레일 5).

Agent에는 쓰기 Tool을 주지 않는다(가드레일 1). 반환은 화면 · LLM에 넘기기 쉬운 dict.
"""

from __future__ import annotations

import functools
from typing import Any

from sqlalchemy.orm import Session

from src.auth.models import User
from src.catalog import service as registry
from src.catalog.models import Asset, AssetStatus
from src.converter.naming import input_schema
from src.monitoring import service as monitoring
from src.monitoring.models import CallLog
from src.shared import trace
from src.shared.errors import NotFound
from src.subscriptions.models import RequestStatus
from src.subscriptions.repository import SubscriptionRepository, ToolRequestRepository
from src.auth.repository import UserRepository
from src.systems.access import effective_role
from src.systems.repository import SystemRepository
from src.systems.service import system_label


def _asset_brief(a: Asset) -> dict[str, Any]:
    return {
        "id": a.id, "name": a.name, "type": a.type.value, "source": a.source.value, "status": a.status.value,
        "system_id": a.system_id, "system_code": a.system.code, "system_name": a.system.name,
    }


LABEL = {
    "list_systems": "시스템 목록", "list_my_systems": "내 담당 시스템", "search_catalog": "카탈로그 검색", "get_asset": "자산 조회",
    "get_asset_detail": "자산 상세", "list_my_access": "내 연계 권한", "get_call_log": "트랜잭션 조회", "query_call_logs": "호출 로그 조회",
    "tool_request_status": "Tool 신청 상태", "system_contacts": "시스템 담당자", "my_role": "내 역할", "users_by_email": "포탈 사용자 확인",
}


def traced(fn):
    """포탈 Tool 호출을 실행 흐름(trace)에 남긴다(결과는 개수만)."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with trace.span("portal", LABEL.get(fn.__name__, fn.__name__)) as s:
            out = fn(self, *args, **kwargs)
            s.detail = f"{len(out)}건" if isinstance(out, list) else ("없음" if out is None else "1건")
            return out
    return wrapper


class PortalTools:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self._systems: dict[int, Any] | None = None

    def _system(self, sid: int | None) -> Any:
        if self._systems is None:
            self._systems = {s.id: s for s in SystemRepository(self.db).search()}
        return self._systems.get(sid) if sid else None

    @traced
    def list_systems(self) -> list[dict[str, Any]]:
        """시스템 목록(포탈의 시스템 화면과 같이 모두 공개). 서버 호스트명 포함."""
        return [{"id": s.id, "code": s.code, "name": s.name, "kind": s.kind.value, "servers": [{"id": v.id, "hostname": v.hostname} for v in s.servers]}
                for s in SystemRepository(self.db).search()]

    @traced
    def my_role(self) -> str:
        """화면 역할(ADMIN · MANAGER · USER)."""
        return effective_role(self.db, self.user)

    @traced
    def users_by_email(self, emails: list[str]) -> list[dict[str, Any]]:
        """포탈에 가입한(사용 중인) 사용자만 이름 · 이메일로 돌려준다."""
        repo = UserRepository(self.db)
        found = [repo.get_by_email(e) for e in emails]
        return [{"id": u.id, "name": u.name, "email": u.email} for u in found if u is not None and u.is_active]

    @traced
    def list_my_systems(self) -> list[dict[str, Any]]:
        """내가 담당자인 시스템(서버 포함)."""
        return [
            {"id": s.id, "code": s.code, "name": s.name, "kind": s.kind.value, "servers": [{"id": v.id, "hostname": v.hostname} for v in s.servers]}
            for s in SystemRepository(self.db).search(managed_by=self.user.id)
        ]

    @traced
    def search_catalog(self, q: str | None = None, live_only: bool = True) -> list[dict[str, Any]]:
        """카탈로그 검색(볼 수 있는 자산만). live_only면 구독 가능한 운영 상태만."""
        return [_asset_brief(a) for a in registry.catalog(self.db, self.user, q, None, AssetStatus.LIVE if live_only else None)]

    @traced
    def get_asset(self, asset_id: int) -> dict[str, Any] | None:
        try:
            a = registry.get_asset(self.db, self.user, asset_id)
        except NotFound:
            return None
        return {**_asset_brief(a), "tools": [t.name for t in a.tools if t.exposed]}

    @traced
    def get_asset_detail(self, asset_id: int) -> dict[str, Any] | None:
        """개발 지원용 상세: 연결 정보 · 리소스 · 공개 Tool(변환 Tool은 입력 스키마 포함)."""
        try:
            a = registry.get_asset(self.db, self.user, asset_id)
        except NotFound:
            return None
        return {
            **_asset_brief(a), "endpoint": a.endpoint or "", "transport": a.transport.value if a.transport else None,
            "auth_type": a.auth_type or "", "base_url": a.base_url or "", "content_type": a.content_type or "application/json",
            "operations": [{"method": o.method.value, "path": o.path, "summary": o.summary} for o in a.operations],
            "tools": [
                {"name": t.name, "description": t.description, "kind": t.kind.value,
                 "input_schema": input_schema(t.source_operation, t.source_operation.asset.layout_fields) if t.source_operation else None}  # 레이아웃은 원본 API의 것
                for t in a.tools if t.exposed
            ],
        }

    @traced
    def list_my_access(self, asset_id: int | None = None) -> list[dict[str, Any]]:
        """내가 쓸 수 있는 승인된 연계: 내 담당 시스템이 클라이언트인 구독, 또는 내가 Tool 권한을 받은 구독."""
        managed = SystemRepository(self.db).managed_ids(self.user.id)
        granted: dict[int, list[str]] = {}
        for tr in ToolRequestRepository(self.db).for_user(self.user.id):
            if tr.status == RequestStatus.APPROVED:
                granted.setdefault(tr.subscription_id, []).append(tr.tool.name)
        subs = {s.id: s for s in SubscriptionRepository(self.db).for_clients(managed, RequestStatus.APPROVED)}
        for sid in granted:
            if sid not in subs:
                s = SubscriptionRepository(self.db).get(sid)
                if s is not None and s.status == RequestStatus.APPROVED:
                    subs[sid] = s
        return [
            {"subscription_id": s.id, "asset_id": s.asset_id, "asset_name": s.asset.name, "client_system_code": s.client_system.code, "my_tools": sorted(granted.get(s.id, []))}
            for s in subs.values() if asset_id is None or s.asset_id == asset_id
        ]

    # ---------- 모니터링 (조회 범위는 monitoring/service.py 규칙) ----------

    def _log(self, lg: CallLog) -> dict[str, Any]:
        c, p = self._system(lg.client_system_id), self._system(lg.provider_system_id)
        return {
            "tx_id": lg.tx_id, "kind": lg.kind.value, "success": lg.success, "code": lg.return_code, "name": lg.name,
            "asset_id": lg.asset_id, "tool_id": lg.tool_id, "subscription_id": lg.subscription_id, "user_id": lg.user_id,
            "client_system_id": lg.client_system_id, "client": system_label(c.code, c.name) if c else "-",
            "provider_system_id": lg.provider_system_id, "provider": system_label(p.code, p.name) if p else "-",
            "started_at": monitoring.as_utc(lg.started_at), "duration_ms": lg.duration_ms, "method": lg.method, "uri": lg.uri,
            "error_message": lg.error_message, "stages": lg.stages or [],
        }

    @traced
    def get_call_log(self, tx_id: str) -> dict[str, Any] | None:
        try:
            return self._log(monitoring.get_log(self.db, self.user, tx_id))
        except NotFound:
            return None

    @traced
    def query_call_logs(self, **filters: Any) -> list[dict[str, Any]]:
        """filters: since, until, failed_only, kind, system_ids, codes, subscription_id, limit"""
        return [self._log(lg) for lg in monitoring.list_logs(self.db, self.user, **filters)]

    @traced
    def tool_request_status(self, user_id: int, subscription_id: int, tool_id: int) -> str | None:
        """그 사용자의 그 Tool 신청 상태(가장 최근). 신청이 없으면 None."""
        rows = [t for t in ToolRequestRepository(self.db).for_user(user_id) if t.subscription_id == subscription_id and t.tool_id == tool_id]
        return max(rows, key=lambda t: t.id).status.value if rows else None

    @traced
    def system_contacts(self, system_id: int) -> list[str]:
        s = self._system(system_id)
        return [f"{m.user.name}({m.user.email})" for m in s.managers] if s else []

    def relay_mcp(self, system_code: str, name: str) -> "MasterClient":
        """A2X Agent 시스템의 승인된 구독으로 그 시스템의 MCP(운영 · 직접 개발)를 A2X 중계로 부르는 클라이언트.
        호출 사용자는 로그인 사용자 — 중계가 시스템 구독 + 사용자 Tool 권한을 확인하고 call_logs에 남긴다."""
        from src.catalog.models import AssetSource, AssetType
        from src.shared.config import settings
        from src.subscriptions.models import SystemSubscription
        from src.tools.master_client import MasterClient, UnavailableClient

        systems = SystemRepository(self.db)
        agent, target = systems.get_by_code(settings.A2X_AGENT_SYSTEM_CODE), systems.get_by_code(system_code)
        if agent is None or target is None:
            return UnavailableClient(name, f"A2X Agent 또는 {system_code} 시스템이 포탈에 없습니다.")
        asset = next((a for a in registry.catalog(self.db, self.user, None, AssetType.MCP, AssetStatus.LIVE)
                      if a.system_id == target.id and a.source == AssetSource.MCP_DIRECT), None)
        if asset is None:
            return UnavailableClient(name, f"{system_code}의 운영 중인 MCP 서버가 카탈로그에 없습니다.")
        sub = self.db.query(SystemSubscription).filter(
            SystemSubscription.client_system_id == agent.id, SystemSubscription.asset_id == asset.id, SystemSubscription.status == RequestStatus.APPROVED,
        ).first()
        if sub is None:
            return UnavailableClient(name, f"A2X Agent의 {asset.name} 시스템 구독이 승인되지 않았습니다.")
        return MasterClient(f"{settings.CONVERTER_PUBLIC_URL.rstrip('/')}/mcp/{asset.id}", name,
                            headers={"X-A2X-User": self.user.email, "X-A2X-Subscription": str(sub.id)}, via_a2x=True, asset_id=asset.id)

