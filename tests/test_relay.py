"""A2X MCP 중계: 직접 개발한 MCP 서버(IRP · DCM)로 가는 호출도 A2X를 거쳐 권한 확인 · 호출 로그를 남긴다."""

import anyio
import pytest

from src.catalog.models import Asset
from src.converter.runtime import ConverterError, ConverterRuntime, Identity
from src.monitoring.models import CallKind, CallLog
from src.subscriptions.models import SystemSubscription
from src.systems.repository import SystemRepository
from src.tools.mock_master.server import dcm as dcm_server, irp as irp_server

HONG, KIM = "hong@example.com", "kim@example.com"


@pytest.fixture()
def relay(seeded, session_factory):
    systems = SystemRepository(seeded)
    a2x = systems.get_by_code("A2X")
    irp_asset = seeded.query(Asset).filter(Asset.name == "IRP 시스템 정보 MCP").one()
    dcm_asset = seeded.query(Asset).filter(Asset.name == "DCM 서버 정보 MCP").one()
    sub = lambda a: seeded.query(SystemSubscription).filter_by(client_system_id=a2x.id, asset_id=a.id).one().id  # noqa: E731
    rt = ConverterRuntime(session_factory, enforce=True, upstream_tokens={},
                          mcp_targets={irp_asset.endpoint: irp_server, dcm_asset.endpoint: dcm_server})
    return {"rt": rt, "irp": irp_asset.id, "dcm": dcm_asset.id, "irp_sub": sub(irp_asset), "dcm_sub": sub(dcm_asset), "a2x": a2x.id, "irp_sys": irp_asset.system_id}


def logs(db):
    db.expire_all()
    return db.query(CallLog).order_by(CallLog.id).all()


def test_relay_lists_only_exposed_tools(relay):
    tools = anyio.run(relay["rt"].list_tools_async, relay["irp"])
    assert sorted(t.name for t in tools) == ["get_system", "search_systems"] and tools[0].input_schema  # 원본 입력 스키마


def test_relay_call_success_is_logged(relay, seeded):
    res = anyio.run(relay["rt"].call_tool, relay["irp"], "get_system", {"system_code": "QMS"}, Identity(HONG, relay["irp_sub"], "10.10.15.11"))
    assert not res.is_error and res.structured_content["dept"] == "품질보증팀"
    log = logs(seeded)[-1]
    assert log.kind == CallKind.MCP and log.success and log.return_code == "200"
    assert log.client_system_id == relay["a2x"] and log.provider_system_id == relay["irp_sys"]  # A2X Agent → IRP
    assert log.name == "IRP 시스템 정보 MCP · get_system" and log.uri.endswith("/irp/mcp") and log.user_id is not None
    assert [s["name"] for s in log.stages] == ["Gateway 수신", "사용자 Tool 권한 확인", "원본 MCP 호출"]
    assert log.response_body["system_code"] == "QMS"


def test_relay_denies_user_without_tool_permission(relay, seeded):
    res = anyio.run(relay["rt"].call_tool, relay["irp"], "get_system", {"system_code": "QMS"}, Identity(KIM, relay["irp_sub"]))
    assert res.is_error and "사용 권한이 없습니다" in res.content[0].text
    log = logs(seeded)[-1]
    assert log.return_code == "403" and not log.success  # 막힌 호출도 남는다


def test_relay_upstream_tool_error_and_unknown_tool(relay, seeded):
    rt = relay["rt"]
    res = anyio.run(rt.call_tool, relay["irp"], "get_system", {"system_code": "NOPE"}, Identity(HONG, relay["irp_sub"]))
    assert res.is_error and logs(seeded)[-1].return_code == "422"  # 원본 MCP Tool 오류
    res = anyio.run(rt.call_tool, relay["dcm"], "drop_all", {}, Identity(HONG, relay["dcm_sub"]))
    assert res.is_error and logs(seeded)[-1].return_code == "404"


def test_relay_tool_level_least_privilege(relay, seeded):
    # 홍길동은 DCM search_servers만 승인 → get_server는 A2X가 막는다(Tool 단위 최소 권한)
    res = anyio.run(relay["rt"].call_tool, relay["dcm"], "get_server", {"hostname": "wms-api01"}, Identity(HONG, relay["dcm_sub"]))
    assert res.is_error and "get_server 사용 권한이 없습니다" in res.content[0].text and logs(seeded)[-1].return_code == "403"


def test_relay_rejects_unknown_asset(relay):
    with pytest.raises(ConverterError):
        anyio.run(relay["rt"].list_tools_async, 99999)


def test_portal_builds_a2x_relay_client(seeded):
    from src.auth.repository import UserRepository
    from src.tools.master_client import UnavailableClient
    from src.tools.portal import PortalTools

    portal = PortalTools(seeded, UserRepository(seeded).get_by_email(HONG))
    c = portal.relay_mcp("IRP", "IRP")
    assert c.via_a2x and "/mcp/" in c.target and c.headers["X-A2X-User"] == HONG and c.headers["X-A2X-Subscription"].isdigit()
    assert c.target.endswith(f"/mcp/{c.asset_id}")  # 권한 오류 때 이 자산의 Tool 신청으로 안내
    assert isinstance(portal.relay_mcp("NOPE", "NOPE"), UnavailableClient)  # 우회하지 않고 이유를 알린다
