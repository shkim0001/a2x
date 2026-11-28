"""샘플 데이터 시드: 샘플 포탈(frontend/src/lib/sample-data.ts)과 같은 데이터를 DB에 넣는다.

실행(저장소 루트에서):
    .venv\\Scripts\\python.exe -m src.seed           # 비어 있을 때만
    .venv\\Scripts\\python.exe -m src.seed --reset   # 모든 행을 지우고 다시
"""

import argparse
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.auth.models import Role, User
from src.auth.security import hash_password
from src.catalog.models import ApiOperation, Asset, AssetSource, AssetStatus, AssetType, HttpMethod, IconKind, McpTool, McpTransport, ToolKind
from src.knowledge.models import ConsultDoc, DocStatus
from src.shared.config import ROOT_DIR, settings
from src.shared.db.base import Base
from src.shared.db.session import SessionLocal
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest
from src.systems.models import DataLevel, Server, ServerEnv, System, SystemKind, SystemManager

# 개발용 공통 비밀번호(시드 사용자 전원). 운영 DB에는 시드를 넣지 않는다.
DEV_PASSWORD = "a2x-demo-1234"

API_BLUE = "#0071e3"
MCP_VIOLET = "#6e4ff6"

# (이름, 이메일, 역할)
USERS = [
    ("관리자", "admin@example.com", Role.ADMIN),
    ("홍길동", "hong@example.com", Role.USER),
    ("최물류", "choi@example.com", Role.USER),
    ("이주문", "lee.order@example.com", Role.USER),
    ("박정산", "park.settle@example.com", Role.USER),
    ("정고객", "jung.cust@example.com", Role.USER),
    ("한인사", "han.hr@example.com", Role.USER),
    ("윤상담", "yoon@example.com", Role.USER),
    ("강구매", "kang@example.com", Role.USER),
    ("서마케", "seo@example.com", Role.USER),
    ("오공급", "oh.scm@example.com", Role.USER),
    ("남조달", "nam.scm@example.com", Role.USER),
    ("문생산", "moon.mes@example.com", Role.USER),
    ("배설비", "bae.mes@example.com", Role.USER),
    ("박계획", "park.plan@example.com", Role.USER),
    ("김민수", "kim@example.com", Role.USER),
    ("이영희", "lee@example.com", Role.USER),
    ("정현장", "jung.field@example.com", Role.USER),
    ("김희령", "kim.heeryeong@example.com", Role.USER),
    ("설두환", "seol.doohwan@example.com", Role.USER),
    ("박자람", "park.jaram@example.com", Role.USER),
    ("김성환", "kim.seonghwan@example.com", Role.USER),
    ("황상기", "hwang.sangki@example.com", Role.USER),
    ("이기완", "lee.kiwan@example.com", Role.USER),
]

B, A = SystemKind.BUSINESS, SystemKind.AGENT
P, S, D = ServerEnv.PROD, ServerEnv.STAGE, ServerEnv.DEV

# code: (이름, 구분, 프로세스, 부서, 담당자, url, 데이터 등급, 설명, 서버[(호스트, ip, port, 용도, 환경)])
SYSTEMS = {
    "ERP": ("ERP", B, "재무", "주문플랫폼팀", ["이주문", "박정산", "김희령", "이기완"], "https://erp.internal.example", DataLevel.CONFIDENTIAL, "주문·정산 기간계",
            [("erp-was01", "10.10.1.11", 8443, "WAS", P), ("erp-was02", "10.10.1.12", 8443, "WAS", P), ("erp-dev01", "10.20.1.11", 8443, "WAS", D)]),
    "WMS": ("WMS", B, "물류", "물류시스템팀", ["홍길동", "최물류", "설두환"], "https://wms.internal.example", DataLevel.INTERNAL, "창고 재고·입출고 관리",
            [("wms-api01", "10.10.2.21", 8080, "API", P), ("wms-mcp01", "10.10.2.31", 9000, "MCP", P)]),
    "CRM": ("CRM", B, "고객서비스", "고객데이터팀", ["정고객", "김희령", "박자람"], "https://crm.internal.example", DataLevel.CONFIDENTIAL, "고객 정보(개인정보 포함)",
            [("crm-api01", "10.10.3.11", 8443, "API", P)]),
    "HR": ("HR", B, "인사", "인사시스템팀", ["한인사", "김성환"], "https://hr.internal.example", DataLevel.CONFIDENTIAL, "조직·인사 정보",
           [("hr-mcp01", "10.10.4.31", 9000, "MCP", P)]),
    "CSBOT": ("CSBOT", A, "고객서비스", "고객지원팀", ["홍길동", "윤상담", "박자람"], "https://csbot.internal.example", DataLevel.INTERNAL, "고객 문의 응대 Agent",
              [("csbot-app01", "10.10.5.11", 443, "Agent", P)]),
    "PURCH": ("PURCH", A, "구매", "구매혁신팀", ["강구매", "황상기"], "https://purch-agent.internal.example", DataLevel.INTERNAL, "발주량 추천 Agent",
              [("purch-dev01", "10.20.6.11", 443, "Agent", D)]),
    "MKT": ("MKT", A, "영업", "마케팅팀", ["서마케", "이기완"], "https://mkt-agent.internal.example", DataLevel.INTERNAL, "고객 세그먼트 분석 Agent",
            [("mkt-app01", "10.10.7.11", 443, "Agent", P)]),
    "SCM": ("SCM", B, "구매", "공급망혁신팀", ["오공급", "남조달", "황상기", "설두환"], "https://scm.internal.example", DataLevel.INTERNAL, "발주 · 공급사 · 수요 예측 관리",
            [("scm-was01", "10.10.8.11", 8443, "WAS", P), ("scm-was02", "10.10.8.12", 8443, "WAS", P), ("scm-mcp01", "10.10.8.31", 9000, "MCP", P), ("scm-stg01", "10.30.8.11", 8443, "WAS", S)]),
    "MES": ("MES", B, "생산", "스마트팩토리팀", ["문생산", "배설비", "김성환", "황상기"], "https://mes.internal.example", DataLevel.CONFIDENTIAL, "작업지시 · 설비 · 생산 실적 관리",
            [("mes-app01", "10.10.9.11", 8080, "API", P), ("mes-app02", "10.10.9.12", 8080, "API", P), ("mes-mcp01", "10.10.9.31", 9000, "MCP", P), ("mes-dev01", "10.20.9.11", 8080, "API", D)]),
    "PLAN": ("PLAN", A, "생산", "생산기획팀", ["박계획", "김성환"], "https://plan-agent.internal.example", DataLevel.INTERNAL, "설비 상태와 작업지시를 보고 생산 계획을 제안하는 Agent",
             [("plan-app01", "10.10.10.11", 443, "Agent", P)]),
    # 외부 정보 원천: Agent가 MCP로 읽어 시스템 · 서버 등록을 자동 채운다
    "IRP": ("IRP", B, "IT 공통", "IT기획팀", ["이기완", "김희령"], "http://localhost:8200/irp", DataLevel.INTERNAL, "전사 IT 자원(시스템) 마스터. 시스템 기본정보 · 담당자 · 데이터 등급",
            [("irp-app01", "10.10.13.11", 8443, "WAS", P), ("irp-mcp01", "10.10.13.31", 9000, "MCP", P)]),
    "DCM": ("DCM", B, "IT 공통", "인프라운영팀", ["설두환", "박자람"], "http://localhost:8200/dcm", DataLevel.INTERNAL, "데이터센터 자산(서버) 관리. 호스트 · IP · 포트 · 환경 · 용도",
            [("dcm-app01", "10.10.14.11", 8443, "WAS", P), ("dcm-mcp01", "10.10.14.31", 9000, "MCP", P)]),
    # A2X 포탈 내장 Agent도 하나의 AI Agent 시스템: 다른 시스템 MCP를 이 시스템의 구독으로 A2X 중계를 거쳐 부른다
    "A2X": ("A2X", A, "IT 공통", "A2X 플랫폼팀", ["관리자"], "http://localhost:8000", DataLevel.INTERNAL, "A2X 포탈 내장 Agent(컨설팅 · 자동 채움 · 개발 지원 · 오류 조치)",
            [("a2x-app01", "10.10.15.11", 8000, "Agent", P)]),
}

LIVE, STAGE, PENDING = AssetStatus.LIVE, AssetStatus.STAGE, AssetStatus.PENDING
R, W = ToolKind.READ, ToolKind.WRITE

# key: dict(system, type, name, status, icon, description, ops[(method, path, summary)] | tools[(name, desc, kind[, source op path])], converted_from)
ASSETS = {
    "order-api": dict(system="ERP", type="API", name="주문 조회 API", status=LIVE, icon="cart", description="주문 번호·기간으로 주문 내역 조회",
                      ops=[("GET", "/orders", "기간별 주문 목록 조회"), ("GET", "/orders/{orderId}", "주문 상세 조회"), ("GET", "/orders/{orderId}/shipments", "주문 배송 현황 조회"), ("POST", "/orders/{orderId}/cancel", "주문 취소")]),
    "stock-mcp": dict(system="WMS", type="MCP", name="재고 MCP 서버", status=LIVE, icon="warehouse", description="창고별 재고 조회·예약",
                      tools=[("get_stock", "품목별 재고 조회", R), ("list_warehouses", "창고 목록 조회", R), ("reserve_stock", "재고 예약", W), ("cancel_reservation", "예약 취소", W)]),
    "customer-api": dict(system="CRM", type="API", name="고객 정보 API", status=LIVE, icon="users", description="고객 기본 정보 조회(개인정보 마스킹)",
                         ops=[("GET", "/customers/{customerId}", "고객 기본 정보 조회"), ("GET", "/customers/{customerId}/contacts", "고객 연락 이력 조회"), ("GET", "/customers/search", "고객 검색")]),
    "org-mcp": dict(system="HR", type="MCP", name="인사 조직도 MCP", status=LIVE, icon="org", description="조직·부서·결재선 조회",
                    tools=[("get_org", "조직도 조회", R), ("find_employee", "임직원 검색", R), ("get_approval_line", "결재선 조회", R)]),
    "inout-api": dict(system="WMS", type="API", name="입출고 API", status=LIVE, icon="truck", description="입고·출고 내역 조회와 등록",
                      ops=[("GET", "/inbounds", "입고 내역 조회"), ("GET", "/outbounds", "출고 내역 조회"), ("POST", "/outbounds", "출고 요청 등록")]),
    "customer-mcp": dict(system="CRM", type="MCP", name="고객 정보 MCP", status=LIVE, icon="users", description="고객 정보 API를 MCP Tool로 변환해 제공", converted_from="customer-api",
                         tools=[("get_customer", "고객 ID로 기본 정보를 조회한다(개인정보 마스킹)", R, "/customers/{customerId}"), ("search_customers", "이름·전화번호 일부로 고객을 검색한다", R, "/customers/search")]),
    "po-api": dict(system="SCM", type="API", name="발주 관리 API", status=LIVE, icon="receipt", description="발주서 조회 · 등록 · 확정",
                   ops=[("GET", "/purchase-orders", "기간 · 공급사별 발주 목록 조회"), ("GET", "/purchase-orders/{poId}", "발주 상세 조회"), ("POST", "/purchase-orders", "발주 등록"), ("PUT", "/purchase-orders/{poId}/confirm", "발주 확정")]),
    "supplier-mcp": dict(system="SCM", type="MCP", name="공급사 정보 MCP", status=LIVE, icon="building", description="공급사 검색 · 평가 등급 · 납기 이력",
                         tools=[("search_suppliers", "품목 · 지역으로 공급사 검색", R), ("get_supplier", "공급사 기본 정보 조회", R), ("get_supplier_rating", "공급사 평가 등급 · 납기 준수율 조회", R)]),
    "forecast-api": dict(system="SCM", type="API", name="수요 예측 API", status=STAGE, icon="workflow", description="품목별 4주 수요 예측값 제공(검증 중)",
                         ops=[("GET", "/forecasts", "품목군별 수요 예측 목록"), ("GET", "/forecasts/{itemId}", "품목 수요 예측 상세")]),
    "wo-api": dict(system="MES", type="API", name="작업지시 API", status=LIVE, icon="doc", description="작업지시 조회 · 생성 · 상태 변경",
                   ops=[("GET", "/work-orders", "라인 · 일자별 작업지시 목록"), ("GET", "/work-orders/{woId}", "작업지시 상세"), ("POST", "/work-orders", "작업지시 생성"), ("PUT", "/work-orders/{woId}/status", "작업지시 상태 변경")]),
    "equip-mcp": dict(system="MES", type="MCP", name="설비 상태 MCP", status=LIVE, icon="factory", description="설비 가동 상태 · 알람 · OEE",
                      tools=[("get_equipment_status", "설비별 가동 · 정지 상태 조회", R), ("list_alarms", "최근 설비 알람 목록 조회", R), ("get_oee", "라인별 설비 종합 효율(OEE) 조회", R), ("reset_alarm", "확인된 알람 해제", W)]),
    "result-api": dict(system="MES", type="API", name="생산 실적 API", status=PENDING, icon="factory", description="LOT별 생산 실적 · 불량 수량",
                       ops=[("GET", "/production-results", "일자 · 라인별 생산 실적"), ("GET", "/production-results/{lotId}", "LOT 실적 상세")]),
    "settle-api": dict(system="ERP", type="API", name="매출 정산 API", status=LIVE, icon="card", description="월별 매출 · 정산 결과 조회",
                       ops=[("GET", "/settlements", "월별 정산 목록"), ("GET", "/settlements/{month}", "월 정산 상세")]),
    "consult-mcp": dict(system="CRM", type="MCP", name="상담 이력 MCP", status=LIVE, icon="doc", description="고객 상담 이력 조회 · 요약 · 후속 조치 등록",
                        tools=[("get_consult_history", "고객별 상담 이력 조회", R), ("summarize_case", "상담 건 요약 조회", R), ("create_followup", "후속 조치 등록", W)]),
    "attend-api": dict(system="HR", type="API", name="근태 조회 API", status=LIVE, icon="org", description="부서 · 개인 근태 현황 조회",
                       ops=[("GET", "/attendance", "부서별 근태 현황"), ("GET", "/attendance/{employeeId}", "개인 근태 상세")]),
    # 외부 정보 원천 MCP(뒤에 두어 기존 자산 ID를 바꾸지 않는다)
    "irp-mcp": dict(system="IRP", type="MCP", name="IRP 시스템 정보 MCP", status=LIVE, icon="doc", description="시스템 기본정보 · 담당자 조회(시스템 등록 자동 채움에 사용)",
                    tools=[("search_systems", "시스템 검색(코드 · 이름 · 부서 · 업무 프로세스)", R), ("get_system", "시스템 상세(담당자 포함)", R)]),
    "dcm-mcp": dict(system="DCM", type="MCP", name="DCM 서버 정보 MCP", status=LIVE, icon="database", description="서버 호스트 · IP · 포트 · 환경 조회(서버 등록 자동 채움에 사용)",
                    tools=[("search_servers", "서버 검색(시스템 코드 · 호스트명 · IP)", R), ("get_server", "서버 상세", R)]),
}

def _business_name(asset_name: str) -> str:
    return asset_name.removesuffix(" API").removesuffix(" MCP").strip()


AP, PE, RJ = RequestStatus.APPROVED, RequestStatus.PENDING, RequestStatus.REJECTED

# key: (클라이언트 시스템, 자산 key, 목적, 신청자, 신청일, 상태)
SUBSCRIPTIONS = {
    "SB-104": ("CSBOT", "order-api", "고객 문의 시 주문 상태 안내", "윤상담", "2026-11-23", PE),
    "SB-103": ("PURCH", "stock-mcp", "발주 추천 시 재고 확인", "강구매", "2026-11-22", PE),
    "SB-102": ("CSBOT", "inout-api", "배송 문의 시 출고 현황 확인", "홍길동", "2026-11-21", AP),
    "SB-101": ("CSBOT", "stock-mcp", "배송 문의 시 재고 확인", "홍길동", "2026-11-20", AP),
    "SB-100": ("CSBOT", "org-mcp", "담당 부서 안내", "홍길동", "2026-11-19", AP),
    "SB-099": ("MKT", "customer-api", "세그먼트 분석", "서마케", "2026-11-18", AP),
    "SB-098": ("CSBOT", "customer-mcp", "문의 고객 확인", "홍길동", "2026-11-17", AP),
    "SB-096": ("PURCH", "order-api", "주문량 기반 발주 추천", "강구매", "2026-11-14", AP),
    "SB-095": ("MKT", "stock-mcp", "재고 연계 프로모션", "서마케", "2026-11-12", RJ),
    "SB-094": ("PURCH", "po-api", "추천 발주안 등록", "강구매", "2026-11-11", AP),
    "SB-093": ("PURCH", "supplier-mcp", "대체 공급사 추천", "강구매", "2026-11-11", AP),
    "SB-092": ("PLAN", "equip-mcp", "설비 상태 기반 생산 계획", "박계획", "2026-11-10", AP),
    "SB-091": ("PLAN", "wo-api", "작업지시 현황 반영", "박계획", "2026-11-23", PE),
    "SB-090": ("CSBOT", "consult-mcp", "상담 이력 기반 응대", "홍길동", "2026-11-09", AP),
    "SB-089": ("MKT", "settle-api", "캠페인 매출 효과 분석", "서마케", "2026-11-08", AP),
    "SB-105": ("A2X", "irp-mcp", "시스템 등록 자동 채움(IRP 시스템 정보 조회)", "관리자", "2026-11-25", AP),
    "SB-106": ("A2X", "dcm-mcp", "시스템 · 서버 등록 자동 채움(DCM 서버 정보 조회)", "관리자", "2026-11-25", AP),
}

# A2X Agent의 IRP · DCM 조회 Tool: 시스템 · 서버 등록은 담당자 기능이라 시스템 담당자 · admin에게 일괄 승인(그 밖의 사용자는 Tool 신청)
A2X_AGENT_TOOLS = {"SB-105": ["search_systems", "get_system"], "SB-106": ["search_servers"]}

# (사용자, 구독 key, Tool, 목적, 신청일, 상태)
TOOL_REQUESTS = [
    ("김민수", "SB-101", "reserve_stock", "상담 중 재고 선점", "2026-11-24", PE),
    ("홍길동", "SB-100", "get_approval_line", "결재선 안내", "2026-11-24", PE),
    ("홍길동", "SB-101", "get_stock", "재고 확인", "2026-11-21", AP),
    ("이영희", "SB-101", "get_stock", "재고 확인", "2026-11-21", AP),
    ("홍길동", "SB-100", "get_org", "담당 부서 안내", "2026-11-19", AP),
    ("강구매", "SB-093", "search_suppliers", "대체 공급사 탐색", "2026-11-12", AP),
    ("강구매", "SB-093", "get_supplier_rating", "공급사 평가 확인", "2026-11-12", AP),
    ("박계획", "SB-092", "get_equipment_status", "가동 설비 확인", "2026-11-11", AP),
    ("박계획", "SB-092", "get_oee", "라인 효율 확인", "2026-11-11", AP),
    ("정현장", "SB-092", "reset_alarm", "현장 알람 처리", "2026-11-22", PE),
    ("홍길동", "SB-090", "get_consult_history", "이전 상담 확인", "2026-11-10", AP),
    ("김민수", "SB-090", "summarize_case", "상담 요약", "2026-11-10", AP),
    ("홍길동", "SB-090", "create_followup", "후속 조치 등록", "2026-11-23", PE),
]

# 컨설팅 샘플 문서(src/knowledge/sample_docs). 색인은 시드 명령 끝에서(테스트의 seed()는 색인하지 않음)
DOCS = [
    ("사내 시스템 연계 표준 가이드 v3.md", "integration-standard-v3.md", "2026-11-10"),
    ("MCP 서버 개발 가이드.md", "mcp-server-dev-guide.md", "2026-11-15"),
    ("API 보안 체크리스트.md", "api-security-checklist.md", "2026-11-22"),
    ("방화벽 신청 절차.md", "firewall-request.md", "2026-11-24"),
    ("A2X 포탈 사용 가이드.md", "portal-guide.md", "2026-11-25"),
]
SAMPLE_DOC_DIR = "src/knowledge/sample_docs"


def _day(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(hour=9, tzinfo=timezone.utc)


def reset(db: Session) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.flush()


def seed(db: Session) -> dict[str, int]:
    pw_hash = hash_password(DEV_PASSWORD)  # bcrypt는 느려서 한 번만 계산해 함께 쓴다
    users = {name: User(name=name, email=email, role=role, password_hash=pw_hash) for name, email, role in USERS}
    db.add_all(users.values())
    db.flush()

    systems: dict[str, System] = {}
    for code, (name, kind, process, dept, managers, url, level, desc, servers) in SYSTEMS.items():
        s = System(code=code, name=name, kind=kind, process=process, dept=dept, url=url, data_level=level, description=desc)
        s.managers = [SystemManager(user=users[m]) for m in managers]
        s.servers = [Server(hostname=h, ip=ip, port=port, role=role, env=env) for h, ip, port, role, env in servers]
        db.add(s)
        systems[code] = s
    db.flush()

    assets: dict[str, Asset] = {}
    for key, a in ASSETS.items():
        typ = AssetType(a["type"])
        source = AssetSource.API if typ == AssetType.API else (AssetSource.MCP_CONVERTED if a.get("converted_from") else AssetSource.MCP_DIRECT)
        sys_ = systems[a["system"]]
        asset = Asset(
            system=sys_, type=typ, source=source, status=a["status"], name=a["name"], description=a["description"],
            icon_kind=IconKind.PRESET, icon_name=a["icon"], icon_color=API_BLUE if typ == AssetType.API else MCP_VIOLET,
            business_category=sys_.process, business_name=_business_name(a["name"]), auth_type="OAuth2 Client Credentials", created_by_id=sys_.managers[0].user.id,
            base_url=f"{sys_.url}/api" if typ == AssetType.API else None, timeout_ms=5000 if typ == AssetType.API else None,
        )
        asset.operations = [ApiOperation(method=HttpMethod(m), path=p, summary=s) for m, p, s in a.get("ops", [])]
        if typ == AssetType.MCP and source == AssetSource.MCP_DIRECT:
            mcp_host = next((sv for sv in sys_.servers if sv.role == "MCP"), None)
            asset.endpoint = f"{sys_.url}/mcp"
            asset.host_server = mcp_host
            asset.transport = McpTransport.STREAMABLE_HTTP
        db.add(asset)
        assets[key] = asset
    db.flush()

    # Tool (변환 Tool은 원본 오퍼레이션을 가리킨다)
    for key, a in ASSETS.items():
        asset = assets[key]
        src = assets.get(a.get("converted_from", ""))
        if src:
            asset.converted_from = src
            asset.endpoint = f"{settings.CONVERTER_PUBLIC_URL.rstrip('/')}/mcp/{asset.id}"
        for t in a.get("tools", []):
            name, desc, kind = t[0], t[1], t[2]
            op = next((o for o in src.operations if o.path == t[3]), None) if src and len(t) > 3 else None
            asset.tools.append(McpTool(name=name, description=desc, kind=kind, source_operation=op))
    db.flush()

    subs: dict[str, SystemSubscription] = {}
    for key, (client, akey, purpose, by, day, status) in SUBSCRIPTIONS.items():
        asset = assets[akey]
        sub = SystemSubscription(client_system=systems[client], asset=asset, purpose=purpose, requested_by_id=users[by].id, status=status, created_at=_day(day))
        if status != PE:
            sub.decided_by_id = asset.system.managers[0].user.id
            sub.decided_at = _day(day)
        db.add(sub)
        subs[key] = sub
    db.flush()

    for user, skey, tool_name, purpose, day, status in TOOL_REQUESTS:
        sub = subs[skey]
        tool = next(t for t in sub.asset.tools if t.name == tool_name)
        tr = ToolRequest(subscription=sub, tool=tool, user=users[user], purpose=purpose, status=status, created_at=_day(day))
        if status != PE:
            tr.decided_by_id = sub.asset.system.managers[0].user.id
            tr.decided_at = _day(day)
        db.add(tr)

    for skey, tools in A2X_AGENT_TOOLS.items():
        sub = subs[skey]
        for name, u in users.items():
            if u.role != Role.ADMIN and not any(m.user_id == u.id for sy in systems.values() for m in sy.managers):
                continue
            for tool_name in tools:
                tool = next(t for t in sub.asset.tools if t.name == tool_name)
                db.add(ToolRequest(subscription=sub, tool=tool, user=u, purpose="A2X Agent 자동 채움(담당자 일괄 승인)", status=AP,
                                   decided_by_id=sub.asset.system.managers[0].user.id, decided_at=_day("2026-11-25"), created_at=_day("2026-11-25")))

    admin = users["관리자"]
    db.add_all([
        ConsultDoc(name=n, file_path=f"{SAMPLE_DOC_DIR}/{f}", uploaded_by_id=admin.id, status=DocStatus.INDEXING,
                   size_bytes=(ROOT_DIR / SAMPLE_DOC_DIR / f).stat().st_size, created_at=_day(d))
        for n, f, d in DOCS
    ])
    db.flush()

    return {"users": len(users), "systems": len(systems), "assets": len(assets), "subscriptions": len(subs), "tool_requests": len(TOOL_REQUESTS), "docs": len(DOCS)}


def main() -> None:
    parser = argparse.ArgumentParser(description="A2X 샘플 데이터 시드")
    parser.add_argument("--reset", action="store_true", help="모든 행을 지우고 다시 넣는다")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reset:
            reset(db)
        elif db.query(System).first():
            print("이미 데이터가 있습니다. 다시 넣으려면 --reset을 붙이세요.")
            return
        counts = seed(db)
        db.commit()
        # 모니터링 샘플 호출 로그(테스트의 seed()에는 넣지 않음: 건수가 많음)
        from src.monitoring.generator import generate

        calls = generate(db)
        db.commit()
        # 컨설팅 문서 색인(임베딩 모델을 읽는다. 실패해도 시드는 끝내고 문서 상태에 남긴다)
        from src.knowledge.store import get_store
        from src.knowledge.service import reindex_all

        indexed = reindex_all(db, get_store())
        db.commit()
    print("시드 완료:", ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"호출 로그: API {calls['api']}건, MCP {calls['mcp']}건(실패 {calls['errors']}건)")
    print("컨설팅 문서 색인:", ", ".join(f"{k} {v}청크" for k, v in indexed.items()))
    print(f"개발용 로그인: hong@example.com (시스템 담당자), admin@example.com (admin), kim@example.com (일반 사용자) / 비밀번호 {DEV_PASSWORD}")


if __name__ == "__main__":
    main()
