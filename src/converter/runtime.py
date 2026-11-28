"""A2X MCP 런타임 (T2-7, Data plane): 모든 MCP 호출이 A2X를 거치게 하는 중계.

- 변환 MCP(자산 출처 MCP_CONVERTED): Tool 호출을 원본 API HTTP 호출로 바꿔 전달한다.
- 직접 개발 MCP(MCP_DIRECT): Tool 호출을 원본 MCP 서버(자산의 엔드포인트)로 그대로 중계한다.
- 실행 대상: 스테이지 · 운영 상태의 변환 MCP 서버
- 권한 집행(설정으로 끌 수 있음): 호출 사용자 · 시스템 구독을 받아 '시스템 구독 승인 + 사용자 Tool 권한'을 확인
- 원본 API 인증: A2X_UPSTREAM_TOKEN_<시스템코드> 환경변수(.env)의 Bearer 토큰
- 모든 호출은 call_logs에 남긴다(인증 정보는 가림)
나중에 Gateway 계층(3차)으로 옮길 수 있도록 포탈 API와 분리된 모듈로 둔다.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from mcp import types
from sqlalchemy.orm import Session, sessionmaker

from src.auth.repository import UserRepository
from src.catalog.models import Asset, AssetSource, AssetStatus, HttpMethod, McpTool, ToolKind
from src.catalog.repository import AssetRepository
from src.converter.naming import input_schema, path_params
from src.monitoring.models import CallKind, CallLog
from src.shared.config import ROOT_DIR
from src.subscriptions.models import SystemSubscription
from src.subscriptions.repository import SubscriptionRepository
from src.subscriptions.service import is_tool_permitted

RUNNABLE = {AssetStatus.STAGE, AssetStatus.LIVE}
TOKEN_PREFIX = "A2X_UPSTREAM_TOKEN_"
MAX_LOG_TEXT = 4000


class ConverterError(Exception):
    """MCP 서버를 찾을 수 없는 등 요청 자체가 성립하지 않는 경우."""


@dataclass
class Identity:
    user_email: str | None = None
    subscription_id: int | None = None
    client_ip: str = ""


@dataclass
class _Stage:
    name: str
    ms: int
    ok: bool


def load_upstream_tokens() -> dict[str, str]:
    """시스템 코드 → 원본 API 토큰. .env와 실제 환경변수(우선)에서 읽는다."""
    values = {**dotenv_values(ROOT_DIR / ".env"), **os.environ}
    return {k[len(TOKEN_PREFIX):].upper(): v for k, v in values.items() if k.startswith(TOKEN_PREFIX) and v}


def _mask(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("Bearer ****" if k.lower() == "authorization" else v) for k, v in headers.items()}


def _log_body(resp: httpx.Response | None) -> Any:
    if resp is None:
        return None
    try:
        return resp.json()
    except ValueError:
        return {"text": resp.text[:MAX_LOG_TEXT]}


class ConverterRuntime:
    def __init__(
        self,
        session_factory: sessionmaker,
        http: httpx.AsyncClient | None = None,
        enforce: bool = True,
        upstream_tokens: dict[str, str] | None = None,
        mcp_targets: dict[str, Any] | None = None,
    ):
        self.session_factory = session_factory
        # 테스트용: 엔드포인트 → 메모리 MCP 서버 객체(없으면 엔드포인트 URL로 Streamable HTTP 접속)
        self.mcp_targets = mcp_targets or {}
        self.http = http or httpx.AsyncClient()
        self.enforce = enforce
        self.tokens = load_upstream_tokens() if upstream_tokens is None else {k.upper(): v for k, v in upstream_tokens.items()}

    # ---------- 조회 ----------

    @staticmethod
    def _load(db: Session, asset_id: int) -> Asset:
        a = AssetRepository(db).get(asset_id)
        ok = a is not None and a.status in RUNNABLE and (
            (a.source == AssetSource.MCP_CONVERTED and a.converted_from is not None) or (a.source == AssetSource.MCP_DIRECT and bool(a.endpoint))
        )
        if not ok:
            raise ConverterError(f"A2X가 중계하는 실행 중인 MCP 서버가 아닙니다: {asset_id}")
        return a

    def _upstream(self, endpoint: str, token: str | None) -> Any:
        """원본 MCP 서버 접속 대상. 토큰이 있으면 Authorization 헤더를 붙인다."""
        if endpoint in self.mcp_targets:
            return self.mcp_targets[endpoint]
        import httpx2
        from mcp.client.streamable_http import streamable_http_client

        from src.tools.master_client import loopback

        headers = {"Authorization": f"Bearer {token}"} if token else None
        return streamable_http_client(loopback(endpoint), http_client=httpx2.AsyncClient(headers=headers, timeout=10))

    async def list_tools_async(self, asset_id: int) -> list[types.Tool]:
        """직접 개발 MCP: 원본 tools/list에서 포탈에 공개(exposed)로 등록된 Tool만 돌려준다(입력 스키마는 원본 것)."""
        with self.session_factory() as db:
            a = self._load(db, asset_id)
            if a.source == AssetSource.MCP_CONVERTED:
                return self.list_tools(asset_id)
            exposed = {t.name for t in a.exposed_tools}
            endpoint, token = a.endpoint, self.tokens.get(a.system.code.upper())
        from mcp.client.client import Client

        async with Client(self._upstream(endpoint, token)) as c:
            tools = (await c.list_tools()).tools
        return [t for t in tools if t.name in exposed]

    def list_tools(self, asset_id: int) -> list[types.Tool]:
        with self.session_factory() as db:
            a = self._load(db, asset_id)
            layout = a.converted_from.layout_fields
            return [
                types.Tool(
                    name=t.name,
                    description=t.description,
                    inputSchema=input_schema(t.source_operation, layout) if t.source_operation else {"type": "object", "properties": {}},
                    annotations=types.ToolAnnotations(readOnlyHint=t.kind == ToolKind.READ, destructiveHint=t.kind == ToolKind.WRITE),
                )
                for t in a.exposed_tools
            ]

    # ---------- 호출 ----------

    async def call_tool(self, asset_id: int, name: str, arguments: dict[str, Any] | None, identity: Identity) -> types.CallToolResult:
        args = dict(arguments or {})
        t0 = time.perf_counter()
        started = datetime.now(timezone.utc)
        stages: list[_Stage] = []
        lap = time.perf_counter()

        def mark(stage: str, ok: bool) -> None:
            nonlocal lap
            now = time.perf_counter()
            stages.append(_Stage(stage, int((now - lap) * 1000), ok))
            lap = now

        with self.session_factory() as db:
            asset = self._load(db, asset_id)
            tool = next((t for t in asset.exposed_tools if t.name == name), None)
            ctx = _CallContext(db=db, asset=asset, tool=tool, identity=identity, args=args, started=started, stages=stages)
            mark("Gateway 수신", True)

            direct = asset.source == AssetSource.MCP_DIRECT
            if tool is None or (not direct and tool.source_operation is None):
                mark("Tool 확인", False)
                return self._finish(ctx, t0, 404, f"공개되지 않았거나 없는 Tool입니다: {name}")

            # 권한 집행: 시스템 구독 승인 + 사용자 Tool 권한
            if self.enforce:
                denied = self._check_permission(ctx)
                mark("사용자 Tool 권한 확인", denied is None)
                if denied:
                    return self._finish(ctx, t0, 403, denied)

            if direct:
                return await self._relay_mcp(ctx, t0, mark)

            # 원본 API 요청 만들기
            op = tool.source_operation
            api = asset.converted_from
            missing = [p for p in path_params(op.path) if p not in args or args[p] in (None, "")]
            if missing:
                mark("입력 검사", False)
                return self._finish(ctx, t0, 400, "필수 경로 파라미터가 없습니다: " + ", ".join(missing))
            path = op.path
            for p in path_params(op.path):
                path = path.replace("{" + p + "}", quote(str(args.pop(p)), safe=""))
            url = (api.base_url or "").rstrip("/") + path
            headers = {"Accept": "application/json"}
            token = self.tokens.get(api.system.code.upper())
            if token:
                headers["Authorization"] = f"Bearer {token}"
            ctx.request_headers = headers
            ctx.uri = url

            timeout = (api.timeout_ms or 10000) / 1000
            try:
                if op.method in (HttpMethod.GET, HttpMethod.DELETE):
                    resp = await self.http.request(op.method.value, url, params=args or None, headers=headers, timeout=timeout)
                else:
                    resp = await self.http.request(op.method.value, url, json=args, headers=headers, timeout=timeout)
            except httpx.TimeoutException:
                mark("원본 API 호출", False)
                return self._finish(ctx, t0, 504, "원본 API 응답 시간 초과")
            except httpx.HTTPError as e:
                mark("원본 API 호출", False)
                return self._finish(ctx, t0, 502, f"원본 API 연결 실패: {type(e).__name__}")

            ok = resp.is_success
            mark("원본 API 호출", ok)
            ctx.response = resp
            return self._finish(ctx, t0, resp.status_code, "" if ok else f"원본 API 오류 {resp.status_code}")

    async def _relay_mcp(self, ctx: "_CallContext", t0: float, mark) -> types.CallToolResult:
        """직접 개발 MCP 서버로 tools/call을 그대로 전달하고 결과를 돌려준다(응답은 구조화 결과 우선으로 기록)."""
        from mcp.client.client import Client

        asset = ctx.asset
        token = self.tokens.get(asset.system.code.upper())
        ctx.request_headers = {"Authorization": f"Bearer {token}"} if token else {}
        ctx.uri = asset.endpoint or ""
        try:
            async with Client(self._upstream(asset.endpoint, token)) as c:
                res = await c.call_tool(ctx.tool.name, ctx.args)
        except TimeoutError:
            mark("원본 MCP 호출", False)
            return self._finish(ctx, t0, 504, "원본 MCP 서버 응답 시간 초과")
        except Exception as e:  # noqa: BLE001 - 연결 실패를 한 가지로 묶는다
            mark("원본 MCP 호출", False)
            return self._finish(ctx, t0, 502, f"원본 MCP 서버 연결 실패: {type(e).__name__}")
        text = "".join(getattr(b, "text", "") for b in res.content)
        ctx.body = res.structured_content if res.structured_content is not None else text[:MAX_LOG_TEXT]
        mark("원본 MCP 호출", not res.is_error)
        if res.is_error:
            return self._finish(ctx, t0, 422, f"원본 MCP Tool 오류: {text[:200]}")
        return self._finish(ctx, t0, 200, "")

    def _check_permission(self, ctx: "_CallContext") -> str | None:
        ident = ctx.identity
        if not ident.user_email or not ident.subscription_id:
            return "호출 사용자와 시스템 구독 정보가 필요합니다."
        user = UserRepository(ctx.db).get_by_email(ident.user_email)
        if user is None:
            return "알 수 없는 사용자입니다."
        sub = SubscriptionRepository(ctx.db).get(ident.subscription_id)
        if sub is None or sub.asset_id != ctx.asset.id:
            return "이 MCP 서버에 대한 시스템 구독이 아닙니다."
        ctx.user_id, ctx.subscription = user.id, sub
        allowed, reason = is_tool_permitted(ctx.db, user.id, sub.id, ctx.tool.name)
        return None if allowed else reason

    def _finish(self, ctx: "_CallContext", t0: float, code: int, error: str) -> types.CallToolResult:
        ok = 200 <= code < 300
        mark_total = int((time.perf_counter() - t0) * 1000)
        body = ctx.body if ctx.body is not None else _log_body(ctx.response)
        sub = ctx.subscription
        ctx.db.add(
            CallLog(
                tx_id=f"CV-{uuid.uuid4().hex[:16]}",
                kind=CallKind.MCP,
                success=ok,
                return_code=str(code),
                name=f"{ctx.asset.name} · {ctx.tool.name if ctx.tool else '?'}",
                asset_id=ctx.asset.id,
                tool_id=ctx.tool.id if ctx.tool else None,
                subscription_id=sub.id if sub else None,
                client_system_id=sub.client_system_id if sub else None,
                provider_system_id=ctx.asset.system_id,
                user_id=ctx.user_id,
                started_at=ctx.started,
                ended_at=datetime.now(timezone.utc),
                duration_ms=mark_total,
                client_ip=ctx.identity.client_ip,
                protocol="MCP",
                method="tools/call",
                uri=ctx.uri or (ctx.asset.endpoint or ""),
                error_message=error,
                request_headers=_mask(ctx.request_headers),
                request_body={"tool": ctx.tool.name if ctx.tool else None, "arguments": ctx.args},
                response_body=body,
                stages=[s.__dict__ for s in ctx.stages],
            )
        )
        ctx.db.commit()
        if ok:
            text = json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else str(body)
            return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structuredContent=body if isinstance(body, dict) else None)
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"[{code}] {error}")], isError=True)


@dataclass
class _CallContext:
    db: Session
    asset: Asset
    tool: McpTool | None
    identity: Identity
    args: dict[str, Any]
    started: datetime
    stages: list[_Stage]
    user_id: int | None = None
    subscription: SystemSubscription | None = None
    request_headers: dict[str, str] | None = None
    uri: str = ""
    response: httpx.Response | None = None
    body: Any = None  # 직접 개발 MCP 중계의 응답(구조화 결과 또는 텍스트)

    def __post_init__(self) -> None:
        self.request_headers = self.request_headers or {}
