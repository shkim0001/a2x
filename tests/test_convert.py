"""T2-6 API → MCP 변환 API, T2-7 컨버터 런타임."""

import json

import anyio
import httpx
import pytest
from mcp.client.client import Client

from src.auth.models import User
from src.catalog.models import Asset, AssetSource, HttpMethod
from src.converter.naming import tool_name
from src.converter.runtime import ConverterError, ConverterRuntime, Identity
from src.converter.server import build_server
from src.monitoring.models import CallLog
from src.subscriptions.models import RequestStatus, ToolRequest

API = "/api/v1"
JUNG = "jung.cust@example.com"  # CRM 담당
HONG, ADMIN, KIM = "hong@example.com", "admin@example.com", "kim@example.com"


# ---------- 규칙: Tool 이름 ----------


@pytest.mark.parametrize(
    "method,path,expected",
    [
        ("GET", "/orders", "list_orders"),
        ("GET", "/orders/{orderId}", "get_order"),
        ("GET", "/orders/{orderId}/shipments", "list_order_shipments"),
        ("POST", "/orders/{orderId}/cancel", "cancel_order"),
        ("GET", "/customers/search", "search_customers"),
        ("GET", "/customers/{customerId}/contacts", "list_customer_contacts"),
        ("POST", "/outbounds", "create_outbound"),
        ("GET", "/stock-history/{itemId}", "get_stock_history"),
        ("PUT", "/purchase-orders/{poId}/confirm", "confirm_purchase_order"),
        ("DELETE", "/categories/{id}", "delete_category"),
    ],
)
def test_tool_name_rule(method, path, expected):
    assert tool_name(HttpMethod(method), path) == expected


# ---------- T2-6 변환 API ----------


def _asset_id(client, h, name):
    return next(a["id"] for a in client.get(f"{API}/assets?q={name}", headers=h).json() if a["name"] == name)


def test_preview_suggests_tools(client, as_user):
    h = as_user(JUNG)
    rows = client.get(f"{API}/assets/{_asset_id(client, h, '고객 정보 API')}/convert/preview", headers=h).json()
    assert [r["tool_name"] for r in rows] == ["get_customer", "list_customer_contacts", "search_customers"]
    assert rows[0]["input_schema"] == {"type": "object", "properties": {"customerId": {"type": "string", "description": "경로 파라미터 customerId"}}, "required": ["customerId"]}
    assert rows[0]["kind"] == "READ" and rows[0]["description"].endswith("읽기 전용.")


def test_convert_creates_mcp_and_goes_through_approval(client, as_user):
    h, admin = as_user(JUNG), as_user(ADMIN)
    api_id = _asset_id(client, h, "고객 정보 API")
    ops = client.get(f"{API}/assets/{api_id}/convert/preview", headers=h).json()
    r = client.post(
        f"{API}/assets/{api_id}/convert",
        headers=h,
        json={"name": "고객 연락 MCP", "tools": [{"operation_id": ops[1]["operation_id"]}, {"operation_id": ops[2]["operation_id"], "name": "find_customers", "description": "고객 찾기"}], "submit": True},
    )
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["source"] == "MCP_CONVERTED" and m["status"] == "PENDING" and m["converted_from_id"] == api_id
    assert [t["name"] for t in m["tools"]] == ["list_customer_contacts", "find_customers"]
    assert m["endpoint"] == f"http://localhost:8100/mcp/{m['id']}"
    assert m["icon"]["name"] == "users"  # 원본 이미지 상속
    assert client.post(f"{API}/assets/{m['id']}/approve", headers=admin).json()["status"] == "STAGE"


def test_convert_rules(client, as_user):
    h = as_user(JUNG)
    api_id = _asset_id(client, h, "고객 정보 API")
    op = client.get(f"{API}/assets/{api_id}/convert/preview", headers=h).json()[0]["operation_id"]
    # 담당자가 아니면 불가
    assert client.post(f"{API}/assets/{api_id}/convert", headers=as_user(HONG), json={"name": "x", "tools": [{"operation_id": op}]}).status_code == 403
    cases = [
        ({"name": "x", "tools": [{"operation_id": 999999}]}, "unknown_operation"),
        ({"name": "x", "tools": [{"operation_id": op, "name": "bad name!"}]}, "invalid_tool_name"),
        ({"name": "x", "tools": [{"operation_id": op, "name": "a"}, {"operation_id": op, "name": "a"}]}, "duplicate_tool"),
        ({"name": "고객 정보 MCP", "tools": [{"operation_id": op}]}, "name_taken"),
    ]
    for body, code in cases:
        r = client.post(f"{API}/assets/{api_id}/convert", headers=h, json=body)
        assert r.status_code in (409, 422) and r.json()["code"] == code, (body, r.text)
    # MCP · 운영 아닌 API는 변환 불가
    mcp_id = _asset_id(client, h, "고객 정보 MCP")
    assert client.get(f"{API}/assets/{mcp_id}/convert/preview", headers=h).json()["code"] == "not_api"
    oh = as_user("oh.scm@example.com")
    stage_api = _asset_id(client, oh, "수요 예측 API")
    assert client.get(f"{API}/assets/{stage_api}/convert/preview", headers=oh).json()["code"] == "api_not_live"


# ---------- T2-7 컨버터 런타임 ----------


def _upstream(log: list):
    """원본 CRM API 흉내."""

    def handler(req: httpx.Request) -> httpx.Response:
        log.append(req)
        if req.url.path == "/api/customers/C1":
            return httpx.Response(200, json={"customerId": "C1", "name": "김**", "grade": "GOLD"})
        if req.url.path == "/api/customers/search":
            return httpx.Response(200, json={"total": 1, "q": req.url.params.get("q")})
        if req.url.path == "/api/customers/BOOM":
            return httpx.Response(500, json={"error": "db down"})
        if req.url.path == "/api/customers/SLOW":
            raise httpx.ReadTimeout("slow", request=req)
        return httpx.Response(404, json={"error": "not found"})

    return handler


@pytest.fixture()
def converted(seeded):
    """시드의 '고객 정보 MCP'(변환, 운영)와 연계 SB-098(CS 챗봇) · 김민수 get_customer 권한."""
    db = seeded
    mcp = db.query(Asset).filter(Asset.source == AssetSource.MCP_CONVERTED).one()
    from src.subscriptions.models import SystemSubscription

    sub = db.query(SystemSubscription).filter(SystemSubscription.asset_id == mcp.id).one()
    kim = db.query(User).filter(User.email == KIM).one()
    tool = next(t for t in mcp.tools if t.name == "get_customer")
    db.add(ToolRequest(subscription_id=sub.id, tool_id=tool.id, user_id=kim.id, purpose="테스트", status=RequestStatus.APPROVED))
    db.commit()
    return {"asset_id": mcp.id, "sub_id": sub.id}


def _runtime(session_factory, log, enforce=True):
    http = httpx.AsyncClient(transport=httpx.MockTransport(_upstream(log)))
    return ConverterRuntime(session_factory, http=http, enforce=enforce, upstream_tokens={"CRM": "secret-crm-token"})


def test_runtime_lists_tools_with_schema(session_factory, converted):
    rt = _runtime(session_factory, [])
    tools = {t.name: t for t in rt.list_tools(converted["asset_id"])}
    assert set(tools) == {"get_customer", "search_customers"}
    assert tools["get_customer"].input_schema["required"] == ["customerId"]
    assert tools["get_customer"].annotations.read_only_hint is True
    with pytest.raises(ConverterError):
        rt.list_tools(9999)


def test_runtime_call_success_maps_to_upstream(session_factory, converted):
    log: list[httpx.Request] = []
    rt = _runtime(session_factory, log)
    ident = Identity(user_email=KIM, subscription_id=converted["sub_id"], client_ip="10.10.5.11")
    res = anyio.run(rt.call_tool, converted["asset_id"], "get_customer", {"customerId": "C1"}, ident)
    assert res.is_error is False and res.structured_content["grade"] == "GOLD"
    req = log[0]
    assert req.method == "GET" and str(req.url) == "https://crm.internal.example/api/customers/C1"
    assert req.headers["authorization"] == "Bearer secret-crm-token"
    with session_factory() as s:
        cl = s.query(CallLog).one()
        assert cl.success and cl.return_code == "200" and cl.user_id is not None and cl.client_system_id is not None
        assert cl.request_headers["Authorization"] == "Bearer ****"  # 토큰은 로그에 남기지 않는다
        assert [st["name"] for st in cl.stages] == ["Gateway 수신", "사용자 Tool 권한 확인", "원본 API 호출"]


def test_runtime_denies_without_permission(session_factory, converted):
    log: list = []
    rt = _runtime(session_factory, log)
    cases = [
        (Identity(), "호출 사용자와 시스템 구독 정보가 필요합니다."),
        (Identity(user_email=HONG, subscription_id=converted["sub_id"]), "사용 권한이 없습니다"),  # 홍길동은 get_customer 권한 없음
        (Identity(user_email=KIM, subscription_id=1), "시스템 구독이 아닙니다"),
    ]
    for ident, msg in cases:
        res = anyio.run(rt.call_tool, converted["asset_id"], "get_customer", {"customerId": "C1"}, ident)
        assert res.is_error and "[403]" in res.content[0].text and msg in res.content[0].text
    assert log == []  # 원본 API는 호출되지 않았다
    with session_factory() as s:
        assert {c.return_code for c in s.query(CallLog)} == {"403"}


def test_runtime_errors(session_factory, converted):
    rt = _runtime(session_factory, [], enforce=False)
    aid = converted["asset_id"]
    call = lambda name, args: anyio.run(rt.call_tool, aid, name, args, Identity())  # noqa: E731
    assert "[400]" in call("get_customer", {}).content[0].text  # 경로 파라미터 없음
    assert "[404]" in call("nope", {}).content[0].text
    assert "[500]" in call("get_customer", {"customerId": "BOOM"}).content[0].text
    assert "[504]" in call("get_customer", {"customerId": "SLOW"}).content[0].text


def test_runtime_query_params_for_get(session_factory, converted):
    log: list[httpx.Request] = []
    rt = _runtime(session_factory, log, enforce=False)
    res = anyio.run(rt.call_tool, converted["asset_id"], "search_customers", {"q": "김"}, Identity())
    assert json.loads(res.content[0].text)["q"] == "김" and log[0].url.params["q"] == "김"


def test_mcp_protocol_end_to_end(session_factory, converted):
    """공식 mcp SDK 클라이언트로 컨버터 MCP 서버에 붙어 tools/list → tools/call."""
    rt = _runtime(session_factory, [])
    ident = Identity(user_email=KIM, subscription_id=converted["sub_id"])
    server = build_server(rt, resolve_asset=lambda ctx: converted["asset_id"], resolve_identity=lambda ctx: ident)

    async def scenario():
        async with Client(server) as c:
            listed = await c.list_tools()
            result = await c.call_tool("get_customer", {"customerId": "C1"})
            return [t.name for t in listed.tools], result

    names, result = anyio.run(scenario)
    assert sorted(names) == ["get_customer", "search_customers"]
    assert result.is_error is False and json.loads(result.content[0].text)["customerId"] == "C1"


def test_asgi_path_router_rejects_bad_path():
    from fastapi.testclient import TestClient

    from src.converter.server import AssetPathRouter

    async def inner(scope, receive, send):  # pragma: no cover - 호출되면 안 됨
        raise AssertionError

    c = TestClient(AssetPathRouter(inner))  # lifespan 없이 요청만
    r = c.post("/not-mcp")
    assert r.status_code == 404
