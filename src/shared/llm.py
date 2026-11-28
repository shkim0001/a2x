"""Claude API 호출 계층 (T0-3).

- 모델은 설정(.env)으로 지정: ANTHROPIC_DEFAULT_MODEL → ANTHROPIC_FALLBACK_MODEL 순서로 시도한다.
- 일시적 장애(429 · 5xx · 529 과부하 · 연결 · 타임아웃 · 모델 없음 404)는 다음 모델로 넘어간다.
  요청 자체가 잘못된 4xx(400 · 401 · 403 · 413 등)는 다른 모델도 똑같이 실패하므로 바로 오류를 낸다.
- Claude Sonnet 5.5에는 서버 측 거절 대비(fallbacks: "default")를 켠다: 안전 분류기가 거절하면
  API가 같은 요청 안에서 다른 모델로 다시 돌린다. 그래도 거절이면 다음 모델(설정)로 넘어간다.
- 규칙 판정은 이 계층을 쓰지 않는다(CLAUDE.md: 판정은 Python 코드, 설명 · 요약에만 LLM).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.shared import trace
from src.shared.config import settings

log = logging.getLogger("a2x.llm")

# 서버 측 거절 대비(fallbacks)를 받는 모델. Claude Sonnet 5.5는 "default" 형식을 쓴다.
SERVER_FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5"}
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(Exception):
    """설정된 모든 모델이 실패했거나 API 키가 없다. 호출부는 규칙 기반 응답으로 대신한다."""


@dataclass
class LLMResult:
    text: str
    model: str  # 실제로 답한 모델(서버 측 대비가 돌았으면 그 모델)
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: list[str] = field(default_factory=list)  # 시도한 모델과 결과
    latency_ms: int = 0


def is_retryable(exc: Exception) -> bool:
    """다른 모델로 넘어가면 해결될 수 있는 오류인가."""
    import anthropic  # 무거운 SDK(Windows에서 import 약 9초)는 실제로 LLM을 부를 때만 불러온다

    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError, anthropic.NotFoundError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code >= 500  # 500 · 529(overloaded) 등
    return False


def has_credentials() -> bool:
    import os

    return bool(settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class LLMClient:
    def __init__(self, client: Any | None = None, models: list[str] | None = None, server_fallback: bool | None = None):
        self.models = [m for m in (models or [settings.ANTHROPIC_DEFAULT_MODEL, settings.ANTHROPIC_FALLBACK_MODEL]) if m]
        self.server_fallback = settings.LLM_SERVER_FALLBACK if server_fallback is None else server_fallback
        self._client = client  # 테스트에서 가짜 클라이언트를 넣는다

    @property
    def client(self):
        if self._client is None:
            if not has_credentials():
                raise LLMUnavailable("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
            import anthropic  # 키가 있을 때만 불러온다(서버 시작 시간 단축)

            # 모델 전환은 이 계층이 하므로 SDK 자체 재시도는 1번으로 줄인다
            self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None, max_retries=1, timeout=settings.LLM_TIMEOUT_SECONDS)
        return self._client

    @property
    def available(self) -> bool:
        return self._client is not None or has_credentials()

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        effort: str | None = None,
        cache_system: bool = True,
    ) -> LLMResult:
        """설정된 모델을 차례로 시도해 텍스트 응답을 돌려준다. 호출 결과는 실행 흐름(trace)에 남긴다."""
        with trace.span("llm", "LLM 호출") as s:
            try:
                r = self._complete(messages, system, max_tokens, effort, cache_system)
            except LLMUnavailable as e:
                s.ok, s.detail = False, f"응답 없음 → 규칙 기반 응답 ({e})"
                raise
            s.detail = f"{r.model} · 입력 {r.input_tokens} · 출력 {r.output_tokens} 토큰" + (f" · {len(r.attempts)}번째 모델" if len(r.attempts) > 1 else "")
            return r

    def _complete(self, messages, system, max_tokens, effort, cache_system) -> LLMResult:
        attempts: list[str] = []
        last: Exception | None = None
        t0 = time.perf_counter()
        sys_param = _system_param(system, cache_system)

        for model in self.models:
            kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
            if sys_param is not None:
                kwargs["system"] = sys_param
            if effort:
                kwargs["output_config"] = {"effort": effort}
            try:
                if self.server_fallback and model in SERVER_FALLBACK_MODELS:
                    resp = self.client.beta.messages.create(betas=[SERVER_FALLBACK_BETA], fallbacks="default", **kwargs)
                else:
                    resp = self.client.messages.create(**kwargs)
            except Exception as e:  # noqa: BLE001 - 분류 후 다시 던진다
                if isinstance(e, LLMUnavailable):
                    raise
                if not is_retryable(e):
                    raise
                attempts.append(f"{model}: {type(e).__name__}")
                log.warning("LLM %s 실패(%s) → 다음 모델", model, type(e).__name__)
                last = e
                continue

            if resp.stop_reason == "refusal":
                # 서버 측 대비까지 거절했다 → 설정의 다음 모델로
                attempts.append(f"{model}: refusal")
                last = None
                continue

            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            attempts.append(f"{model}: ok")
            usage = getattr(resp, "usage", None)
            return LLMResult(
                text=text,
                model=getattr(resp, "model", model),
                stop_reason=resp.stop_reason,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                attempts=attempts,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        raise LLMUnavailable("모든 모델이 응답하지 못했습니다: " + "; ".join(attempts)) from last


def _system_param(system: str | list[dict[str, Any]] | None, cache: bool) -> Any:
    """시스템 프롬프트는 고정 내용이므로 캐시 지점을 붙인다(접두사가 같으면 재사용)."""
    if system is None:
        return None
    if isinstance(system, str):
        block: dict[str, Any] = {"type": "text", "text": system}
        if cache:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]
    return system


_default: LLMClient | None = None


def get_llm() -> LLMClient:
    global _default
    if _default is None:
        _default = LLMClient()
    return _default


def note_skipped(reason: str = "API 키 없음 → 규칙 기반 응답") -> None:
    """LLM을 부르지 않고 넘어간 경우도 실행 흐름에 남긴다(화면에서 '왜 LLM이 안 나왔는지' 보이게)."""
    trace.step("llm", "LLM 호출 생략", reason, ok=False)
