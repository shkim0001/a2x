"""T3-5 개발 지원 Agent: 시드 DB의 실제 자산 · 권한으로 템플릿을 채운다(LLM 없이 / 가짜 LLM)."""

import ast
from types import SimpleNamespace

import anyio
import pytest

from src.agents.devsupport import agent as devsupport
from src.agents.devsupport.templates import example_args
from src.agents.state import UserCtx
from src.auth.repository import UserRepository
from src.tools.portal import PortalTools


@pytest.fixture()
def ctx(seeded):
    def make(email):
        u = UserRepository(seeded).get_by_email(email)
        return PortalTools(seeded, u), UserCtx(id=u.id, name=u.name, email=u.email, role="USER")
    return make


def run(message, portal, user, asset_id=None, llm=None):
    return anyio.run(lambda: devsupport.run(message, portal, user, llm=llm, asset_id=asset_id))


def code_blocks(answer, lang):
    return [b.split("\n", 1)[1].split("```", 1)[0] for b in answer.split("```" + lang)[1:]]


def test_converted_mcp_uses_real_subscription_and_valid_python(ctx):
    portal, user = ctx("hong@example.com")
    r = run("고객 정보 MCP get_customer 호출 코드 예시 알려줘", portal, user)
    py = code_blocks(r.answer, "python")[0]
    ast.parse(py)  # 문법이 맞는 코드
    assert 'URL = "http://localhost:8100/mcp/6"' in py
    assert '"X-A2X-User": "hong@example.com"' in py and '"X-A2X-Subscription": "7"' in py
    assert 'call_tool("get_customer", {"customerId": "<customerId>"})' in py
    assert "'get_customer' Tool 권한이 아직 없습니다" in r.answer  # 구독 #7에서 Tool 권한 없음
    assert '"method": "tools/call"' in code_blocks(r.answer, "bash")[0]
    assert r.sources[0]["id"] == 6 and r.used_llm is None


def test_direct_mcp_uses_token_placeholder(ctx):
    portal, user = ctx("hong@example.com")
    r = run("python 코드 보여줘", portal, user, asset_id=2)  # 재고 MCP 서버(직접 개발)
    py = code_blocks(r.answer, "python")[0]
    assert '"Authorization": "Bearer <YOUR_TOKEN>"' in py and "X-A2X" not in py
    assert "```bash" not in r.answer  # python만 요청
    assert "직접 운영하는 MCP 서버" in r.answer


def test_api_asset_curl_and_python(ctx):
    portal, user = ctx("hong@example.com")
    r = run("주문 상세 /orders/{orderId} 호출 예시", portal, user, asset_id=1)
    assert 'curl -s -X GET "https://erp.internal.example/api/orders/<orderId>"' in r.answer
    ast.parse(code_blocks(r.answer, "python")[0])
    assert "먼저 카탈로그에서 시스템 구독을 신청하세요" in r.answer  # hong은 ERP 구독 없음


def test_no_subscription_placeholder(ctx):
    portal, user = ctx("kim@example.com")
    r = run("고객 정보 MCP curl 예시", portal, user)
    assert "X-A2X-Subscription: <SUBSCRIPTION_ID>" in r.answer and "승인된 시스템 구독이 없어" in r.answer


def test_portal_api_template(ctx):
    portal, user = ctx("kim@example.com")
    r = run("포탈 API로 권한 확인하는 코드", portal, user)
    assert "/api/v1/auth/login" in r.answer and "/api/v1/permissions/check?subscription_id=14" in r.answer
    assert "<YOUR_PASSWORD>" in r.answer and "a2x-demo" not in r.answer


def test_unknown_target_asks(ctx):
    portal, user = ctx("hong@example.com")
    r = run("코드 예시 줘", portal, user)
    assert "어떤 API · MCP" in r.answer and r.actions and r.actions[0]["type"] == "ask"


def test_llm_adds_explanation_only(ctx):
    calls = []

    class FakeLLM:
        available = True

        def complete(self, messages, system=None, **kw):
            calls.append(messages[0]["content"])
            return SimpleNamespace(text="구독 승인 후 Tool을 신청하고 호출하세요.", model="claude-sonnet-5-5")

    portal, user = ctx("hong@example.com")
    r = run("고객 정보 MCP 호출 코드", portal, user, llm=FakeLLM())
    assert r.used_llm == "claude-sonnet-5-5" and "구독 승인 후 Tool을 신청" in r.answer
    assert "```python" in r.answer  # 코드는 템플릿 그대로
    assert "hong@example.com" not in calls[0]  # LLM에는 개인 식별 값을 보내지 않는다


def test_example_args():
    schema = {"type": "object", "properties": {"id": {"type": "string"}, "limit": {"type": "integer"}, "x": {"type": "boolean"}, "y": {"type": "string"}, "z": {"type": "string"}}, "required": ["z"]}
    assert example_args(schema) == {"z": "<z>", "id": "<id>", "limit": 1, "x": True}
    assert example_args(None) == {}


def test_message_asset_wins_over_screen_context(ctx):
    portal, user = ctx("hong@example.com")
    r = run("고객 정보 MCP 호출 python 코드 예시", portal, user, asset_id=2)  # 화면에선 재고 MCP 서버를 열어 둔 상태
    assert r.sources[0]["id"] == 6 and "http://localhost:8100/mcp/6" in r.answer
    r = run("이거 호출 코드 예시", portal, user, asset_id=2)  # 메시지가 특정하지 않으면 화면 문맥
    assert r.sources[0]["id"] == 2
