"""컨버터 MCP 서버 (공식 mcp SDK) · ASGI 앱.

실행(저장소 루트에서, 포탈 API와 별도 프로세스):
    .venv\\Scripts\\python.exe -m uvicorn src.converter.server:app --port 8100

엔드포인트: http://localhost:8100/mcp/{자산ID}  (Streamable HTTP)
호출 헤더: X-A2X-User (사용자 이메일), X-A2X-Subscription (시스템 구독 ID)
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from sqlalchemy import text

from src.converter.runtime import ConverterError, ConverterRuntime, Identity
from src.shared.config import settings
from src.shared.db.session import SessionLocal

ASSET_SCOPE_KEY = "a2x.asset_id"
PATH_RE = re.compile(r"^/mcp/(\d+)/?$")

AssetResolver = Callable[[ServerRequestContext], int]
IdentityResolver = Callable[[ServerRequestContext], Identity]


def asset_from_scope(ctx: ServerRequestContext) -> int:
    req = ctx.request
    if req is None or ASSET_SCOPE_KEY not in req.scope:
        raise MCPError(types.INVALID_REQUEST, "MCP 서버 경로(/mcp/{자산ID})가 필요합니다.")
    return req.scope[ASSET_SCOPE_KEY]


def identity_from_headers(ctx: ServerRequestContext) -> Identity:
    req = ctx.request
    if req is None:
        return Identity()
    sub = req.headers.get("x-a2x-subscription", "")
    return Identity(
        user_email=req.headers.get("x-a2x-user") or None,
        subscription_id=int(sub) if sub.isdigit() else None,
        client_ip=req.client.host if req.client else "",
    )


def build_server(runtime: ConverterRuntime, resolve_asset: AssetResolver = asset_from_scope, resolve_identity: IdentityResolver = identity_from_headers) -> Server:
    async def on_list_tools(ctx: ServerRequestContext, _params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        try:
            return types.ListToolsResult(tools=await runtime.list_tools_async(resolve_asset(ctx)))
        except ConverterError as e:
            raise MCPError(types.INVALID_PARAMS, str(e)) from e

    async def on_call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            return await runtime.call_tool(resolve_asset(ctx), params.name, params.arguments, resolve_identity(ctx))
        except ConverterError as e:
            raise MCPError(types.INVALID_PARAMS, str(e)) from e

    return Server("a2x-converter", version="0.1.0", description="A2X API → MCP 컨버터", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


STARTED_AT = time.time()


def health() -> dict:
    """인스턴스 모니터링용 상태: 권한 판정에 쓰는 DB(구독 · Tool 권한)를 읽을 수 있는지, 가동 시간, 집행 설정."""
    t0 = time.perf_counter()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        policy_db, policy_ms = "ok", round((time.perf_counter() - t0) * 1000)
    except Exception as e:  # noqa: BLE001 — 상태 보고용
        policy_db, policy_ms = f"error: {type(e).__name__}", None
    return {
        "status": "ok" if policy_db == "ok" else "degraded",
        "component": "A2X MCP runtime (권한 Gateway + MCP/API 중계)",
        "uptime_s": round(time.time() - STARTED_AT),
        "enforce_permissions": settings.CONVERTER_ENFORCE_PERMISSIONS,
        "policy_db": policy_db,
        "policy_db_ms": policy_ms,
    }


class AssetPathRouter:
    """/mcp/{자산ID} 요청을 MCP 앱의 /mcp로 넘기고, 자산 ID를 요청 scope에 실어 보낸다. /health는 상태 확인."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/health":
            body = json.dumps(health(), ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json; charset=utf-8")]})
            await send({"type": "http.response.body", "body": body})
            return
        if scope["type"] == "http":
            m = PATH_RE.match(scope["path"])
            if not m:
                await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": '{"detail": "경로는 /mcp/{자산ID} 입니다."}'.encode()})
                return
            scope = {**scope, "path": "/mcp", "raw_path": b"/mcp", ASSET_SCOPE_KEY: int(m.group(1))}
        await self.inner(scope, receive, send)


def create_app(runtime: ConverterRuntime | None = None):
    runtime = runtime or ConverterRuntime(SessionLocal, enforce=settings.CONVERTER_ENFORCE_PERMISSIONS)
    security = (
        TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=settings.CONVERTER_ALLOWED_HOSTS)
        if settings.CONVERTER_ALLOWED_HOSTS
        else TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    inner = build_server(runtime).streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,  # 요청마다 독립(세션 상태를 두지 않아 여러 프로세스로 늘리기 쉽다)
        json_response=True,
        transport_security=security,
    )
    return AssetPathRouter(inner)


app = create_app()
