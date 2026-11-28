"""T0-3 LLM 클라이언트: 모델 전환 · 서버 측 거절 대비 · 오류 분류 (실제 API를 부르지 않는 가짜 클라이언트)."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from src.shared.llm import SERVER_FALLBACK_BETA, LLMClient, LLMUnavailable, is_retryable

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls, code):
    return cls("err", response=httpx2.Response(code, request=REQ), body=None)


def msg(text="안녕하세요", model="claude-sonnet-5-5", stop="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        model=model,
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class FakeMessages:
    def __init__(self, script):
        self.script, self.calls = script, []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClient:
    """messages.create 와 beta.messages.create가 같은 순서표를 공유한다."""

    def __init__(self, script):
        self.messages = FakeMessages(script)
        self.beta = SimpleNamespace(messages=self.messages)


MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5"]


def test_first_model_ok_uses_server_fallback_and_cache():
    fc = FakeClient([msg()])
    r = LLMClient(client=fc, models=MODELS).complete([{"role": "user", "content": "hi"}], system="시스템", effort="low")
    assert r.text == "안녕하세요" and r.model == "claude-sonnet-5-5" and r.attempts == ["claude-sonnet-5-5: ok"]
    call = fc.messages.calls[0]
    assert call["betas"] == [SERVER_FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["output_config"] == {"effort": "low"}
    assert "thinking" not in call  # 최신 모델은 기본 adaptive, 끄지 않는다


@pytest.mark.parametrize(
    "error",
    [
        status_error(anthropic.RateLimitError, 429),
        status_error(anthropic.InternalServerError, 500),
        status_error(anthropic.APIStatusError, 529),
        status_error(anthropic.NotFoundError, 404),
        anthropic.APIConnectionError(request=REQ),
        anthropic.APITimeoutError(request=REQ),
    ],
)
def test_transient_errors_fall_back_to_next_model(error):
    fc = FakeClient([error, msg("대체 응답", model="claude-haiku-5-5")])
    r = LLMClient(client=fc, models=MODELS).complete([{"role": "user", "content": "hi"}])
    assert r.text == "대체 응답" and r.model == "claude-haiku-5-5"
    assert len(r.attempts) == 2 and r.attempts[1] == "claude-haiku-5-5: ok"
    assert "betas" not in fc.messages.calls[1]  # Haiku 5.5에는 서버 측 대비를 쓰지 않는다


@pytest.mark.parametrize("cls,code", [(anthropic.BadRequestError, 400), (anthropic.AuthenticationError, 401), (anthropic.PermissionDeniedError, 403)])
def test_client_errors_raise_immediately(cls, code):
    fc = FakeClient([status_error(cls, code), msg()])
    with pytest.raises(cls):
        LLMClient(client=fc, models=MODELS).complete([{"role": "user", "content": "hi"}])
    assert len(fc.messages.calls) == 1  # 다른 모델로 넘어가지 않는다


def test_refusal_moves_to_next_model():
    fc = FakeClient([msg("", stop="refusal"), msg("대체 응답", model="claude-haiku-5-5")])
    r = LLMClient(client=fc, models=MODELS).complete([{"role": "user", "content": "hi"}])
    assert r.attempts == ["claude-sonnet-5-5: refusal", "claude-haiku-5-5: ok"]


def test_all_models_fail():
    fc = FakeClient([status_error(anthropic.InternalServerError, 500), status_error(anthropic.RateLimitError, 429)])
    with pytest.raises(LLMUnavailable) as ei:
        LLMClient(client=fc, models=MODELS).complete([{"role": "user", "content": "hi"}])
    assert "InternalServerError" in str(ei.value) and "RateLimitError" in str(ei.value)


def test_no_credentials(monkeypatch):
    from src.shared.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    c = LLMClient(models=MODELS)
    assert c.available is False
    with pytest.raises(LLMUnavailable):
        c.complete([{"role": "user", "content": "hi"}])


def test_server_fallback_can_be_disabled():
    fc = FakeClient([msg()])
    LLMClient(client=fc, models=MODELS, server_fallback=False).complete([{"role": "user", "content": "hi"}])
    assert "betas" not in fc.messages.calls[0]


def test_is_retryable_classification():
    assert is_retryable(status_error(anthropic.APIStatusError, 503))
    assert not is_retryable(status_error(anthropic.UnprocessableEntityError, 422))
    assert not is_retryable(ValueError("x"))
