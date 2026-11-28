"""외부 마스터 MCP 클라이언트. Agent는 마스터를 MCP Tool로 읽는다(1차는 모의 MCP 서버).

- 운영: settings.MASTER_MCP_URL (Streamable HTTP)
- 테스트: 서버 객체를 넘기면 메모리 안에서 바로 연결한다
"""

from __future__ import annotations

import json
from typing import Any

from mcp.client.client import Client

from src.shared import trace
from src.shared.config import settings


class MasterError(Exception):
    """마스터 조회 실패(서버 꺼짐, 없는 코드 등). 자동 채움은 이 경우 '마스터에서 찾지 못함'으로 답한다.
    asset_id: A2X 중계로 부른 카탈로그 MCP 자산(권한 오류 때 그 자산의 Tool 신청 화면으로 안내)."""

    def __init__(self, message: str = "", asset_id: int | None = None):
        super().__init__(message)
        self.asset_id = asset_id


def loopback(url: str) -> str:
    """내부 호출용: Windows에서 'localhost'는 IPv6(::1)를 먼저 시도해 약 1초씩 늦어지므로 127.0.0.1로 바로 접속한다."""
    return url.replace("://localhost:", "://127.0.0.1:", 1)


class MasterClient:
    """외부 시스템 MCP 클라이언트. name은 실행 흐름(trace)에 보이는 대상 이름(master · IRP · DCM)."""

    def __init__(self, target: Any | None = None, name: str = "master", headers: dict[str, str] | None = None, via_a2x: bool = False,
                 asset_id: int | None = None):
        self.target = target if target is not None else settings.MASTER_MCP_URL
        self.name = name
        self.headers = headers or {}  # A2X 중계 호출: X-A2X-User · X-A2X-Subscription
        self.via_a2x = via_a2x
        self.asset_id = asset_id  # A2X 중계로 부르는 카탈로그 자산

    @classmethod
    def irp(cls, target: Any | None = None) -> "MasterClient":
        return cls(target if target is not None else settings.IRP_MCP_URL, "IRP")

    @classmethod
    def dcm(cls, target: Any | None = None) -> "MasterClient":
        return cls(target if target is not None else settings.DCM_MCP_URL, "DCM")

    async def call(self, tool: str, **args: Any) -> Any:
        """MCP tools/call. 호출 · 결과 요약은 실행 흐름(trace)에 남긴다."""
        with trace.span(f"mcp:{self.name}", f"tools/call · {tool}" + (" (A2X 중계)" if self.via_a2x else "")) as s:
            shown = ", ".join(f"{k}={v}" for k, v in args.items())
            try:
                out = await self._call(tool, **args)
            except MasterError as e:
                s.ok, s.detail = False, f"({shown}) 실패: {e}"
                if e.asset_id is None:
                    e.asset_id = self.asset_id
                raise
            size = f"{len(out)}건" if isinstance(out, list) else "1건" if out else "없음"
            s.detail = f"({shown}) → {size}"
            return out

    async def _call(self, tool: str, **args: Any) -> Any:
        target = loopback(self.target) if isinstance(self.target, str) else self.target
        if isinstance(target, str) and self.headers:
            import httpx2
            from mcp.client.streamable_http import streamable_http_client

            target = streamable_http_client(target, http_client=httpx2.AsyncClient(headers=self.headers, timeout=15))
        try:
            async with Client(target) as c:
                res = await c.call_tool(tool, args)
        except Exception as e:  # noqa: BLE001 - 연결 실패를 한 가지 오류로 묶는다
            raise MasterError(f"{self.name} MCP 서버에 연결할 수 없습니다: {type(e).__name__}") from e
        if res.is_error:
            raise MasterError(res.content[0].text if res.content else f"{tool} 실패")
        if res.structured_content is not None:
            sc = res.structured_content
            # 목록 반환 Tool은 {"result": [...]} 형태로 감싸여 온다
            return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
        text = res.content[0].text if res.content else ""
        try:
            return json.loads(text)
        except ValueError:
            return text


class UnavailableClient(MasterClient):
    """중계 경로를 만들 수 없을 때(구독 · 자산 없음) — A2X를 우회하지 않고 이유를 알린다."""

    def __init__(self, name: str, reason: str):
        super().__init__("unavailable", name)
        self.reason = reason

    async def call(self, tool: str, **args: Any) -> Any:
        trace.step(f"mcp:{self.name}", f"tools/call · {tool}", self.reason, ok=False)
        raise MasterError(self.reason)
