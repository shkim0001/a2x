"""모니터링 도메인 입출력 스키마(사용내역 · 트랜잭션 상세 · 통계 · 요약)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SystemRef(BaseModel):
    id: int | None
    code: str
    name: str


class CallRow(BaseModel):
    tx_id: str
    kind: str
    success: bool
    return_code: str
    name: str
    client_system: SystemRef
    provider_system: SystemRef
    user: str | None
    user_login: str | None = None  # 호출 사용자 로그인 ID(이메일)
    subscription_id: int | None
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    client_ip: str
    protocol: str
    method: str
    uri: str
    error_message: str


class Classification(BaseModel):
    category: str
    side: str
    action: str


class CallDetail(CallRow):
    request_headers: dict[str, Any] | None
    request_body: Any
    response_body: Any
    stages: list[dict[str, Any]]
    classification: Classification | None


class StatRow(BaseModel):
    key: str
    label: str
    api: int
    mcp: int
    errors: int
    avg_ms: int


class RecentError(BaseModel):
    name: str
    code: str
    category: str
    count: int


class Summary(BaseModel):
    today_calls: int
    today_errors: int
    today_error_rate: float
    failed_24h: int
    recent_errors: list[RecentError]


class CallPage(BaseModel):
    """사용내역 한 페이지."""

    items: list[CallRow]
    total: int
    page: int
    size: int

