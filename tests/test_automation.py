"""T3-4 프로세스 자동화 Agent: 시드 DB(포탈 내부 Tool) + 메모리 모의 마스터 MCP 서버. LLM 없이 규칙만으로 동작."""

import anyio
import pytest

from src.agents.automation import agent as automation
from src.auth.repository import UserRepository
from src.catalog.schemas import ApiAssetIn, McpAssetIn
from src.systems.repository import SystemRepository
from src.tools.master_client import MasterClient, MasterError
from src.tools.mock_master.server import dcm as dcm_server, irp as irp_server, server as master_server
from src.tools.portal import PortalTools


@pytest.fixture()
def tools_for(seeded):
    return lambda email: PortalTools(seeded, UserRepository(seeded).get_by_email(email))


def run(message, portal, page=None, asset_id=None, master=None, irp=None, dcm=None):
    return anyio.run(lambda: automation.run(message, portal, master or MasterClient(master_server), page=page, asset_id=asset_id,
                                             irp=irp or MasterClient.irp(irp_server), dcm=dcm or MasterClient.dcm(dcm_server)))


def test_detect_form_message_over_page():
    assert automation.detect_form("채워줘", "publish") == "api"
    assert automation.detect_form("MCP 서버 등록 채워줘", "publish") == "mcp"
    assert automation.detect_form("ERP 주문 조회 구독 신청해줘", None) == "subscription"
    assert automation.detect_form("채워줘", "home") is None


def test_api_autofill_from_master_is_valid_and_not_submitted(tools_for):
    r = run("WMS 재고 이력 API 등록 채워줘", tools_for("hong@example.com"), page="publish")
    fs = r.form_suggestion
    assert fs["form"] == "api" and fs["source"]["key"] == "WMS-STOCK-HIS"
    v = fs["values"]
    assert v["system_id"] == 2 and v["name"] == "재고 이력 API" and len(v["operations"]) == 2
    assert v["business"]["program"] == "WMS_STK_HIS_010" and v["base_url"].startswith("https://wms")
    assert "submit" not in v
    ApiAssetIn.model_validate(v)  # 포탈 등록 API가 받는 형태 그대로
    assert "제출은 하지 않았습니다" in r.answer and r.actions[0] == {"type": "open", "page": "publish", "label": "API 등록 화면에서 확인"}
    assert r.used_tools == ["portal.list_my_systems", "master.search_apis", "master.get_api"]


def test_api_ambiguous_asks_instead_of_guessing(tools_for):
    r = run("WMS API 등록 채워줘", tools_for("hong@example.com"))
    assert r.form_suggestion is None
    assert {a["label"] for a in r.actions} == {"재고 이력 API (WMS-STOCK-HIS)", "출고 관리 API (WMS-OUTBOUND)"}


def test_multiple_systems_ask_which(seeded, tools_for):
    systems = SystemRepository(seeded)
    systems.add_manager(systems.get_by_code("MES"), UserRepository(seeded).get_by_email("hong@example.com"))
    seeded.commit()
    r = run("API 등록 채워줘", tools_for("hong@example.com"))  # 업무 시스템 WMS · MES 담당(CSBOT은 Agent 시스템이라 제외)
    assert r.form_suggestion is None and [a["label"] for a in r.actions] == ["WMS", "MES"]


def test_cannot_register_for_unmanaged_system(tools_for):
    r = run("ERP 주문 조회 API 등록 채워줘", tools_for("kim@example.com"))
    assert r.form_suggestion is None and "업무 시스템의 담당자만" in r.answer


def test_mcp_autofill_maps_host_server_and_flags_write_tool(seeded, tools_for):
    systems = SystemRepository(seeded)
    systems.add_manager(systems.get_by_code("MES"), UserRepository(seeded).get_by_email("hong@example.com"))
    seeded.commit()
    r = run("MES 품질 추적 MCP 등록 채워줘", tools_for("hong@example.com"), page="mcp-register")
    v = r.form_suggestion["values"]
    McpAssetIn.model_validate(v)
    assert v["name"] == "품질 추적 MCP" and [t["name"] for t in v["tools"]] == ["get_lot_trace", "list_quality_issues", "hold_lot"]
    mes = systems.get_by_code("MES")
    assert v["host_server_id"] == next(s.id for s in mes.servers if s.hostname == "mes-mcp01")
    assert any("hold_lot" in n for n in r.form_suggestion["notes"])


def test_mcp_not_in_master(tools_for):
    r = run("WMS MCP 등록 채워줘", tools_for("hong@example.com"))
    assert "MCP 서버 마스터에 WMS 시스템의 MCP 서버가 없습니다" in r.answer
    assert r.form_suggestion["values"] == {"system_id": 2}


def test_subscription_from_catalog_context(tools_for):
    r = run("이거 구독 신청 채워줘", tools_for("hong@example.com"), page="catalog", asset_id=1)  # ERP 주문 조회 API
    assert r.form_suggestion is None and [a["label"] for a in r.actions] == ["WMS", "CSBOT"]
    r = run("CSBOT으로 구독 신청 채워줘", tools_for("hong@example.com"), page="catalog", asset_id=1)
    v = r.form_suggestion["values"]
    assert v["client_system_id"] == 5 and v["asset_id"] == 1 and v["purpose"]


def test_subscription_skips_own_system_and_searches_catalog(tools_for):
    # 재고 MCP 서버는 WMS 자산 → 클라이언트 후보는 CSBOT 하나
    r = run("재고 MCP 서버 구독 신청 채워줘", tools_for("hong@example.com"))
    v = r.form_suggestion["values"]
    assert v["asset_id"] == 2 and v["client_system_id"] == 5
    assert any("Tool을 따로 신청" in n for n in r.form_suggestion["notes"])


def test_subscription_requires_client_manager(tools_for):
    r = run("주문 조회 API 구독 신청 채워줘", tools_for("kim@example.com"))
    assert r.form_suggestion is None and "클라이언트 시스템의 담당자" in r.answer


def test_master_down_falls_back_to_manual(tools_for):
    r = run("WMS 재고 이력 API 등록 채워줘", tools_for("hong@example.com"), master=MasterClient("http://127.0.0.1:1/mcp"))
    assert r.form_suggestion is None and "외부 시스템 MCP를 읽지 못해" in r.answer


def test_subscription_message_wins_over_screen_context(tools_for):
    r = run("재고 MCP 서버 구독 신청 채워줘", tools_for("hong@example.com"), page="catalog", asset_id=1)
    assert r.form_suggestion["values"]["asset_id"] == 2



# ---------- 시스템 등록(IRP + DCM) · 서버 등록(DCM) ----------

def test_detect_system_and_server_forms():
    assert automation.detect_form("QMS 시스템 등록 채워줘", None) == "system"
    assert automation.detect_form("wms-batch01 서버 등록해줘", None) == "server"
    assert automation.detect_form("MCP 서버 등록 채워줘", None) == "mcp"  # MCP 서버는 MCP 등록
    assert automation.detect_form("채워줘", "systems") == "system" and automation.detect_form("채워줘", "servers") == "server"


def test_system_autofill_from_irp_and_dcm(tools_for):
    from src.systems.schemas import SystemIn

    r = run("QMS 시스템 등록 채워줘", tools_for("hong@example.com"), page="systems")
    fs = r.form_suggestion
    v = fs["values"]
    assert fs["form"] == "system" and v["code"] == "QMS" and v["dept"] == "품질보증팀" and v["process"] == "생산"
    assert {sv["hostname"] for sv in v["servers"]} == {"qms-was01", "qms-was02", "qms-dev01"}  # DCM
    assert set(v["manager_emails"]) == {"kim.seonghwan@example.com", "bae.mes@example.com"}  # 포탈 가입자만
    assert {m["name"] for m in v["managers"]} == {"김성환", "배설비"}
    assert any("노품질" in n for n in fs["notes"])  # 미가입 담당자 안내
    SystemIn.model_validate({k: x for k, x in v.items() if k != "managers"})
    assert "제출은 하지 않았습니다" in r.answer


def test_system_autofill_lists_unregistered_and_rejects_registered(tools_for):
    r = run("시스템 등록 채워줘", tools_for("hong@example.com"))
    assert r.form_suggestion is None and {a["message"].split()[0] for a in r.actions} == {"QMS", "PLM"}
    r = run("WMS 시스템 등록 채워줘", tools_for("hong@example.com"))
    assert r.form_suggestion is None and "이미 포탈에 등록된 시스템" in r.answer


def test_server_autofill_from_dcm(tools_for):
    from src.systems.schemas import ServerIn

    r = run("WMS 서버 등록 채워줘", tools_for("hong@example.com"))  # WMS에 아직 없는 서버 2대 → 선택지
    assert r.form_suggestion is None and {a["message"].split()[1] for a in r.actions} == {"wms-batch01", "wms-stg01"}
    r = run("wms-batch01 서버 등록 채워줘", tools_for("hong@example.com"))  # 호스트명으로 시스템까지 특정
    v = r.form_suggestion["values"]
    assert r.form_suggestion["form"] == "server" and v["hostname"] == "wms-batch01" and v["ip"] == "10.10.2.41" and v["env"] == "PROD"
    assert v["system_id"] == 2
    ServerIn.model_validate({k: x for k, x in v.items() if k != "system_id"})


def test_anyone_can_fill_system_form_but_server_needs_a_system(tools_for):
    # 시스템 등록은 누구나(등록하면 담당자가 됨), 서버 추가는 담당 시스템이 있어야 한다
    r = run("QMS 시스템 등록 채워줘", tools_for("kim@example.com"))
    assert r.form_suggestion and r.form_suggestion["form"] == "system"
    r = run("wms-batch01 서버 등록해줘", tools_for("kim@example.com"))
    assert r.form_suggestion is None and "담당 시스템이 있어야" in r.answer


def test_system_form_servers_only_from_dcm(tools_for):
    assert automation.detect_form("QMS 시스템 서버 채워줘", "systems") == "system_servers"
    assert automation.detect_form("시스템 등록 서버 채워줘", None) == "system_servers"
    r = run("PLM 시스템 서버 채워줘", tools_for("hong@example.com"), page="systems")
    fs = r.form_suggestion
    assert fs["form"] == "system_servers" and fs["values"]["code"] == "PLM"
    assert [s["hostname"] for s in fs["values"]["servers"]] == ["plm-app01", "plm-stg01"]
    assert set(fs["values"]) == {"code", "servers"}  # 서버 정보만(다른 입력값은 건드리지 않음)


def test_system_form_servers_needs_code_and_unregistered_system(tools_for):
    r = run("시스템 서버 채워줘", tools_for("hong@example.com"), page="systems")
    assert r.form_suggestion is None and "시스템 코드를 먼저 입력" in r.answer
    r = run("WMS 시스템 서버 채워줘", tools_for("hong@example.com"), page="systems")
    assert r.form_suggestion is None and "이미 포탈에 등록된 시스템" in r.answer
    r = run("NEWSYS 시스템 서버 채워줘", tools_for("hong@example.com"), page="systems")
    assert r.form_suggestion is None and "DCM에 NEWSYS 시스템의 서버가 없습니다" in r.answer



def test_permission_denied_points_to_catalog_request(tools_for):
    # A2X 중계가 Tool 권한 없음으로 막으면, 그 MCP 서버를 담은 카탈로그 사용 신청 화면으로 안내한다
    class Denied(MasterClient):
        async def call(self, tool, **args):
            raise MasterError("사용자 Tool 권한이 없습니다: search_systems", asset_id=42)

    r = run("QMS 시스템 등록 채워줘", tools_for("hong@example.com"), irp=Denied("x", "IRP"))
    assert r.form_suggestion is None
    assert {"type": "request", "asset_id": "42", "label": "Tool 사용 신청"} in r.actions
