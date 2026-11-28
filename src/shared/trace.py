"""실행 흐름 기록(트레이스): 한 요청 안에서 모듈끼리 주고받은 호출을 순서대로 남긴다.

Agent 채팅 화면이 시퀀스 다이어그램으로 보여 준다(누가 → 누구에게 · 무엇을 · 결과 · 걸린 시간).
- 참여자 ID: user, guard, supervisor, agent:<route>, portal(포탈 Tool), rag(ChromaDB), mcp(외부 마스터 MCP), llm(Claude)
- contextvars로 요청마다 따로 모은다. 기록 중이 아니면(테스트 · 다른 진입점) 아무것도 하지 않는다.
- 비밀 값 · 개인정보는 detail에 넣지 않는다(요약 · 개수 · 이름만).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_steps: ContextVar[list[dict[str, Any]] | None] = ContextVar("a2x_trace_steps", default=None)
_actor: ContextVar[str] = ContextVar("a2x_trace_actor", default="agent")
DETAIL_MAX = 160


@contextmanager
def collecting() -> Iterator[list[dict[str, Any]]]:
    """이 블록 안의 기록을 모아 돌려준다."""
    token = _steps.set([])
    try:
        yield _steps.get()  # type: ignore[misc]
    finally:
        _steps.reset(token)


@contextmanager
def acting(actor: str) -> Iterator[None]:
    """이 블록 안에서 호출하는 쪽(src)을 정한다(예: agent:consult)."""
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)


def actor() -> str:
    return _actor.get()


def step(dst: str, label: str, detail: str = "", ok: bool = True, ms: int | None = None, src: str | None = None) -> None:
    steps = _steps.get()
    if steps is None:
        return
    steps.append({"seq": len(steps) + 1, "src": src or _actor.get(), "dst": dst, "label": label,
                  "detail": detail[:DETAIL_MAX], "ok": ok, "ms": ms})


class Span:
    def __init__(self) -> None:
        self.detail = ""
        self.ok = True


@contextmanager
def span(dst: str, label: str, src: str | None = None) -> Iterator[Span]:
    """호출 하나를 감싸 걸린 시간과 결과를 남긴다. 예외가 나면 실패로 기록하고 다시 던진다."""
    s, t0 = Span(), time.perf_counter()
    try:
        yield s
    except Exception as e:
        s.ok, s.detail = False, s.detail or f"{type(e).__name__}"
        raise
    finally:
        step(dst, label, s.detail, s.ok, int((time.perf_counter() - t0) * 1000), src)
