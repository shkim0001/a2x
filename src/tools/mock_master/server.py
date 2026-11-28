"""모의 외부 시스템 MCP 서버 (공식 mcp SDK). 한 프로세스에서 세 MCP 서버를 띄운다.

- 마스터(API · MCP 서버 마스터, 담당자 연락처): http://localhost:8200/mcp
- IRP(전사 IT 자원 · 시스템 마스터):           http://localhost:8200/irp/mcp
- DCM(데이터센터 서버 자산):                    http://localhost:8200/dcm/mcp
Tool 목록은 AGENTS.md 4.2. 1차는 가짜 데이터(data.py), 실제 시스템으로 바꿀 때 Tool 이름 · 입력 · 출력은 유지한다.

실행(저장소 루트에서): .venv\\Scripts\\python.exe -m uvicorn src.tools.mock_master.server:app --port 8200
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette

from src.tools.mock_master import data

READ_ONLY = ToolAnnotations(readOnlyHint=True)

server = MCPServer(name="a2x-mock-master", version="0.1.0", description="A2X 모의 외부 마스터(API · MCP 서버 마스터 · 담당자 연락처)")


def _match(q: str, *values: str) -> bool:
    ql = q.strip().lower()
    return not ql or any(ql in (v or "").lower() for v in values)


@server.tool(annotations=READ_ONLY)
def search_apis(system_code: str = "", query: str = "") -> list[dict[str, Any]]:
    """API 마스터에서 API를 찾는다. 시스템 코드로 좁히고 이름 · 업무명으로 검색한다."""
    return [
        {"api_code": code, "system_code": a["system_code"], "name": a["name"], "business_name": a["business"]["name"]}
        for code, a in data.APIS.items()
        if (not system_code or a["system_code"] == system_code.upper()) and _match(query, code, a["name"], a["business"]["name"], a["description"])
    ]


@server.tool(annotations=READ_ONLY)
def get_api(api_code: str) -> dict[str, Any]:
    """API 마스터 상세: 업무정보, 데이터 방향, Base URL, 인증 방식, 리소스, 요청 · 응답 필드(API 등록 양식과 같은 형태)."""
    a = data.APIS.get(api_code.upper())
    if a is None:
        raise ToolError(f"API 마스터에 없는 코드입니다: {api_code}")
    return {"api_code": api_code.upper(), **a}


@server.tool(annotations=READ_ONLY)
def get_mcp_server(system_code: str, name: str = "") -> list[dict[str, Any]]:
    """MCP 서버 마스터: 전송 방식, 엔드포인트, 인증, 서버, Tool 목록(MCP 등록 양식과 같은 형태). 이름을 비우면 시스템의 전체 목록."""
    return [m for (code, n), m in data.MCP_SERVERS.items() if code == system_code.upper() and _match(name, n)]


@server.tool(annotations=READ_ONLY)
def get_contact(dept: str) -> dict[str, Any]:
    """부서 담당자와 연락처(이메일 · 전화 · 채널). 컨설팅 Agent의 '담당자 문의' 안내에 쓴다."""
    for d, c in data.CONTACTS.items():
        if _match(dept, d):
            return {"dept": d, **c}
    return {"dept": "A2X 플랫폼팀", **data.CONTACTS["A2X 플랫폼팀"]}


# ---------- IRP: 전사 IT 자원(시스템) 마스터 ----------

irp = MCPServer(name="irp", version="0.1.0", description="IRP 전사 IT 자원 마스터(모의): 시스템 기본정보 · 담당자 · 데이터 등급")


@irp.tool(annotations=READ_ONLY)
def search_systems(query: str = "") -> list[dict[str, Any]]:
    """IRP에서 시스템을 찾는다. 코드 · 이름 · 부서 · 업무 프로세스 · 설명으로 검색한다."""
    return [
        {"system_code": code, "name": s["name"], "dept": s["dept"], "process": s["process"], "kind": s["kind"], "description": s["description"]}
        for code, s in data.SYSTEMS.items()
        if _match(query, code, s["name"], s["dept"], s["process"], s["description"])
    ]


@irp.tool(annotations=READ_ONLY)
def get_system(system_code: str) -> dict[str, Any]:
    """IRP 시스템 상세: 이름, 구분, 업무 프로세스, 부서, 데이터 등급, 서비스 URL, 설명, 담당자(이름 · 이메일)."""
    s = data.SYSTEMS.get(system_code.upper())
    if s is None:
        raise ToolError(f"IRP에 없는 시스템 코드입니다: {system_code}")
    return {"system_code": system_code.upper(), **s}


# ---------- DCM: 데이터센터 서버 자산 ----------

dcm = MCPServer(name="dcm", version="0.1.0", description="DCM 데이터센터 자산 관리(모의): 서버 호스트 · IP · 포트 · 환경 · 용도")


@dcm.tool(annotations=READ_ONLY)
def search_servers(system_code: str = "", query: str = "") -> list[dict[str, Any]]:
    """DCM에서 서버를 찾는다. 시스템 코드로 좁히고 호스트명 · IP · 용도 · 환경으로 검색한다."""
    return [
        sv for sv in data.SERVERS
        if (not system_code or sv["system_code"] == system_code.upper()) and _match(query, sv["hostname"], sv["ip"], sv["role"], sv["env"])
    ]


@dcm.tool(annotations=READ_ONLY)
def get_server(hostname: str) -> dict[str, Any]:
    """DCM 서버 상세(호스트명으로)."""
    for sv in data.SERVERS:
        if sv["hostname"] == hostname.lower():
            return sv
    raise ToolError(f"DCM에 없는 서버입니다: {hostname}")


# ---------- 한 앱으로 조립 ----------

_SECURITY = TransportSecuritySettings(enable_dns_rebinding_protection=False)  # 개발용: 로컬 접속만 받는다(배포 시 allowed_hosts 지정)
_SUBAPPS = [
    m.streamable_http_app(streamable_http_path=path, stateless_http=True, json_response=True, transport_security=_SECURITY)
    for m, path in ((server, "/mcp"), (irp, "/irp/mcp"), (dcm, "/dcm/mcp"))
]


@asynccontextmanager
async def _lifespan(app):
    async with AsyncExitStack() as stack:
        for sub in _SUBAPPS:  # 각 MCP 서버의 세션 관리자를 함께 띄운다
            await stack.enter_async_context(sub.router.lifespan_context(sub))
        yield


app = Starlette(routes=[r for sub in _SUBAPPS for r in sub.routes], lifespan=_lifespan)
