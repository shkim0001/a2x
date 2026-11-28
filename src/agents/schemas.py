"""A2X Agent 채팅 API 입출력 스키마."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatContext(BaseModel):
    page: str | None = Field(default=None, max_length=50)
    asset_id: int | None = None
    transaction_id: str | None = Field(default=None, max_length=40)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: ChatContext = ChatContext()
    history: list[Turn] = Field(default=[], max_length=10)


class TraceStep(BaseModel):
    """실행 흐름 한 단계: src가 dst에게 label을 보냈고 결과가 detail(시퀀스 다이어그램의 화살표 하나)."""

    seq: int
    src: str  # user · guard · supervisor · agent:<route> · portal · rag · mcp · llm
    dst: str
    label: str
    detail: str
    ok: bool
    ms: int | None


class ChatOut(BaseModel):
    route: str
    rule: str
    answer: str
    sources: list[dict[str, Any]]
    form_suggestion: dict[str, Any] | None
    actions: list[dict[str, Any]]
    used_llm: str | None
    guard_notes: list[str]
    trace: list[TraceStep] = []
