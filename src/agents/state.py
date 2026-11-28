"""Agent 공통 상태 · 결과 형식."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


@dataclass
class UserCtx:
    """Agent는 로그인 사용자 권한으로만 동작한다(가드레일 5)."""

    id: int
    name: str
    email: str
    role: str  # USER | MANAGER | ADMIN (화면 역할: admin은 저장, MANAGER는 담당 시스템 유무로 계산)
    managed_system_ids: list[int] = field(default_factory=list)


@dataclass
class AgentResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)  # 근거(문서 · 데이터)
    form_suggestion: dict[str, Any] | None = None  # 자동 채움 제안(제출하지 않음)
    actions: list[dict[str, str]] = field(default_factory=list)  # 화면 이동 등 다음 행동 제안
    used_tools: list[str] = field(default_factory=list)
    used_llm: str | None = None  # 실제 답한 모델(없으면 규칙 기반 응답)


class AgentState(TypedDict, total=False):
    message: str
    history: list[dict[str, str]]
    page: str | None
    asset_id: int | None
    transaction_id: str | None
    user: UserCtx
    route: str
    rule: str
    result: AgentResult
    check: Any  # guard.RequestCheck (전처리 판정)
    guard_notes: list[str]
    trace: list[dict[str, Any]]  # 실행 흐름(shared/trace.py) — 화면의 시퀀스 다이어그램
