"""모의 외부 시스템 MCP 서버(마스터 · IRP · DCM) + Agent용 MCP 클라이언트."""

import anyio
import pytest

from src.tools.master_client import MasterClient, MasterError
from src.tools.mock_master.server import app, dcm, irp, server


def call(tool, target=server, **args):
    return anyio.run(lambda: MasterClient(target).call(tool, **args))


def tool_names(target):
    async def names():
        from mcp.client.client import Client

        async with Client(target) as c:
            return sorted(t.name for t in (await c.list_tools()).tools)

    return anyio.run(names)


def test_tool_list_matches_agents_md():
    assert tool_names(server) == ["get_api", "get_contact", "get_mcp_server", "search_apis"]
    assert tool_names(irp) == ["get_system", "search_systems"]
    assert tool_names(dcm) == ["get_server", "search_servers"]
    assert [r.path for r in app.routes] == ["/mcp", "/irp/mcp", "/dcm/mcp"]  # 한 프로세스, 세 엔드포인트


def test_irp_systems():
    rows = call("search_systems", irp, query="물류")
    assert [r["system_code"] for r in rows] == ["WMS"]
    wms = call("get_system", irp, system_code="wms")
    assert wms["dept"] == "물류시스템팀" and wms["managers"][0]["email"] == "hong@example.com"
    assert {"QMS", "PLM"} <= {r["system_code"] for r in call("search_systems", irp)}  # 포탈에 아직 없는 시스템


def test_dcm_servers():
    wms = call("search_servers", dcm, system_code="WMS")
    assert {"wms-api01", "wms-mcp01", "wms-batch01"} <= {s["hostname"] for s in wms}
    assert call("get_server", dcm, hostname="qms-was01")["system_code"] == "QMS"
    with pytest.raises(MasterError, match="DCM에 없는 서버"):
        call("get_server", dcm, hostname="nope")


def test_apis():
    assert {r["api_code"] for r in call("search_apis", system_code="WMS")} == {"WMS-STOCK-HIS", "WMS-OUTBOUND"}
    api = call("get_api", api_code="WMS-STOCK-HIS")
    assert api["business"]["program"] == "WMS_STK_HIS_010" and api["operations"][1]["path"] == "/stock-history/{itemId}"


def test_mcp_server_and_contact():
    m = call("get_mcp_server", system_code="MES", name="품질")
    assert m[0]["endpoint"].endswith("/mcp/quality") and [t["kind"] for t in m[0]["tools"]] == ["READ", "READ", "WRITE"]
    assert call("get_contact", dept="보안")["channel"] == "#security"
    assert call("get_contact", dept="없는팀")["dept"] == "A2X 플랫폼팀"  # 모르면 플랫폼팀으로 안내


def test_unknown_code_is_error():
    with pytest.raises(MasterError, match="없는 코드"):
        call("get_api", api_code="NOPE")


def test_unreachable_server():
    with pytest.raises(MasterError, match="연결할 수 없습니다"):
        anyio.run(lambda: MasterClient("http://127.0.0.1:1/mcp").call("search_apis"))
