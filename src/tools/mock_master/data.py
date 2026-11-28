"""모의 외부 시스템 데이터(가짜): IRP(시스템 마스터) · DCM(서버 자산) · API/MCP 마스터 · 담당자 연락처.
실제 시스템으로 바꿀 때 Tool의 입력 · 출력 형태는 유지한다.

포탈 시드(src/seed.py)의 시스템 코드와 맞추고, 자동 채움 시연을 위해
아직 포탈에 등록되지 않은 API · MCP 마스터도 넣어 둔다(재고 이력 API, 품질 추적 MCP 등).
"""

# IRP(전사 IT 자원 마스터): 시스템 기본정보 · 담당자. 시스템 등록 양식에 대응
SYSTEMS = {
    "ERP": {"name": "ERP", "kind": "BUSINESS", "process": "재무", "dept": "주문플랫폼팀", "data_level": "CONFIDENTIAL",
            "url": "https://erp.internal.example", "description": "주문·정산 기간계",
            "managers": [{"name": "이주문", "email": "lee.order@example.com"}, {"name": "박정산", "email": "park.settle@example.com"}, {"name": "김희령", "email": "kim.heeryeong@example.com"}, {"name": "이기완", "email": "lee.kiwan@example.com"}]},
    "WMS": {"name": "WMS", "kind": "BUSINESS", "process": "물류", "dept": "물류시스템팀", "data_level": "INTERNAL",
            "url": "https://wms.internal.example", "description": "창고 재고·입출고 관리",
            "managers": [{"name": "홍길동", "email": "hong@example.com"}, {"name": "최물류", "email": "choi@example.com"}, {"name": "설두환", "email": "seol.doohwan@example.com"}]},
    "CRM": {"name": "CRM", "kind": "BUSINESS", "process": "고객서비스", "dept": "고객데이터팀", "data_level": "CONFIDENTIAL",
            "url": "https://crm.internal.example", "description": "고객 정보(개인정보 포함)",
            "managers": [{"name": "정고객", "email": "jung.cust@example.com"}, {"name": "김희령", "email": "kim.heeryeong@example.com"}, {"name": "박자람", "email": "park.jaram@example.com"}]},
    "HR": {"name": "HR", "kind": "BUSINESS", "process": "인사", "dept": "인사시스템팀", "data_level": "CONFIDENTIAL",
            "url": "https://hr.internal.example", "description": "조직·인사 정보",
            "managers": [{"name": "한인사", "email": "han.hr@example.com"}, {"name": "김성환", "email": "kim.seonghwan@example.com"}]},
    "CSBOT": {"name": "CSBOT", "kind": "AGENT", "process": "고객서비스", "dept": "고객지원팀", "data_level": "INTERNAL",
            "url": "https://csbot.internal.example", "description": "고객 문의 응대 Agent",
            "managers": [{"name": "홍길동", "email": "hong@example.com"}, {"name": "윤상담", "email": "yoon@example.com"}, {"name": "박자람", "email": "park.jaram@example.com"}]},
    "PURCH": {"name": "PURCH", "kind": "AGENT", "process": "구매", "dept": "구매혁신팀", "data_level": "INTERNAL",
            "url": "https://purch-agent.internal.example", "description": "발주량 추천 Agent",
            "managers": [{"name": "강구매", "email": "kang@example.com"}, {"name": "황상기", "email": "hwang.sangki@example.com"}]},
    "MKT": {"name": "MKT", "kind": "AGENT", "process": "영업", "dept": "마케팅팀", "data_level": "INTERNAL",
            "url": "https://mkt-agent.internal.example", "description": "고객 세그먼트 분석 Agent",
            "managers": [{"name": "서마케", "email": "seo@example.com"}, {"name": "이기완", "email": "lee.kiwan@example.com"}]},
    "SCM": {"name": "SCM", "kind": "BUSINESS", "process": "구매", "dept": "공급망혁신팀", "data_level": "INTERNAL",
            "url": "https://scm.internal.example", "description": "발주 · 공급사 · 수요 예측 관리",
            "managers": [{"name": "오공급", "email": "oh.scm@example.com"}, {"name": "남조달", "email": "nam.scm@example.com"}, {"name": "황상기", "email": "hwang.sangki@example.com"}, {"name": "설두환", "email": "seol.doohwan@example.com"}]},
    "MES": {"name": "MES", "kind": "BUSINESS", "process": "생산", "dept": "스마트팩토리팀", "data_level": "CONFIDENTIAL",
            "url": "https://mes.internal.example", "description": "작업지시 · 설비 · 생산 실적 관리",
            "managers": [{"name": "문생산", "email": "moon.mes@example.com"}, {"name": "배설비", "email": "bae.mes@example.com"}, {"name": "김성환", "email": "kim.seonghwan@example.com"}, {"name": "황상기", "email": "hwang.sangki@example.com"}]},
    "PLAN": {"name": "PLAN", "kind": "AGENT", "process": "생산", "dept": "생산기획팀", "data_level": "INTERNAL",
            "url": "https://plan-agent.internal.example", "description": "설비 상태와 작업지시를 보고 생산 계획을 제안하는 Agent",
            "managers": [{"name": "박계획", "email": "park.plan@example.com"}, {"name": "김성환", "email": "kim.seonghwan@example.com"}]},
    "QMS": {"name": "QMS", "kind": "BUSINESS", "process": "생산", "dept": "품질보증팀", "data_level": "CONFIDENTIAL",
            "url": "https://qms.internal.example", "description": "품질 검사 · 불량 · 시정조치(CAPA) 관리",
            "managers": [{"name": "김성환", "email": "kim.seonghwan@example.com"}, {"name": "배설비", "email": "bae.mes@example.com"}, {"name": "노품질", "email": "noh.qa@example.com"}]},
    "PLM": {"name": "PLM", "kind": "BUSINESS", "process": "생산", "dept": "제품개발팀", "data_level": "CONFIDENTIAL",
            "url": "https://plm.internal.example", "description": "제품 BOM · 설계 변경(ECO) · 도면 관리",
            "managers": [{"name": "황상기", "email": "hwang.sangki@example.com"}, {"name": "이기완", "email": "lee.kiwan@example.com"}, {"name": "진설계", "email": "jin.design@example.com"}]},
    "IRP": {"name": "IRP", "kind": "BUSINESS", "process": "IT 공통", "dept": "IT기획팀", "data_level": "INTERNAL",
            "url": "http://localhost:8200/irp", "description": "전사 IT 자원(시스템) 마스터. 시스템 기본정보 · 담당자 · 데이터 등급",
            "managers": [{"name": "이기완", "email": "lee.kiwan@example.com"}, {"name": "김희령", "email": "kim.heeryeong@example.com"}]},
    "DCM": {"name": "DCM", "kind": "BUSINESS", "process": "IT 공통", "dept": "인프라운영팀", "data_level": "INTERNAL",
            "url": "http://localhost:8200/dcm", "description": "데이터센터 자산(서버) 관리. 호스트 · IP · 포트 · 환경 · 용도",
            "managers": [{"name": "설두환", "email": "seol.doohwan@example.com"}, {"name": "박자람", "email": "park.jaram@example.com"}]},
}

# DCM(데이터센터 자산 관리): 서버 호스트 · IP · 포트 · 환경 · 용도. 서버 등록 양식에 대응
SERVERS = [
    {"hostname": "erp-was01", "ip": "10.10.1.11", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "ERP"},
    {"hostname": "erp-was02", "ip": "10.10.1.12", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "ERP"},
    {"hostname": "erp-dev01", "ip": "10.20.1.11", "port": 8443, "env": "DEV", "role": "WAS", "system_code": "ERP"},
    {"hostname": "wms-api01", "ip": "10.10.2.21", "port": 8080, "env": "PROD", "role": "API", "system_code": "WMS"},
    {"hostname": "wms-mcp01", "ip": "10.10.2.31", "port": 9000, "env": "PROD", "role": "MCP", "system_code": "WMS"},
    {"hostname": "crm-api01", "ip": "10.10.3.11", "port": 8443, "env": "PROD", "role": "API", "system_code": "CRM"},
    {"hostname": "hr-mcp01", "ip": "10.10.4.31", "port": 9000, "env": "PROD", "role": "MCP", "system_code": "HR"},
    {"hostname": "csbot-app01", "ip": "10.10.5.11", "port": 443, "env": "PROD", "role": "Agent", "system_code": "CSBOT"},
    {"hostname": "purch-dev01", "ip": "10.20.6.11", "port": 443, "env": "DEV", "role": "Agent", "system_code": "PURCH"},
    {"hostname": "mkt-app01", "ip": "10.10.7.11", "port": 443, "env": "PROD", "role": "Agent", "system_code": "MKT"},
    {"hostname": "scm-was01", "ip": "10.10.8.11", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "SCM"},
    {"hostname": "scm-was02", "ip": "10.10.8.12", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "SCM"},
    {"hostname": "scm-mcp01", "ip": "10.10.8.31", "port": 9000, "env": "PROD", "role": "MCP", "system_code": "SCM"},
    {"hostname": "scm-stg01", "ip": "10.30.8.11", "port": 8443, "env": "STAGE", "role": "WAS", "system_code": "SCM"},
    {"hostname": "mes-app01", "ip": "10.10.9.11", "port": 8080, "env": "PROD", "role": "API", "system_code": "MES"},
    {"hostname": "mes-app02", "ip": "10.10.9.12", "port": 8080, "env": "PROD", "role": "API", "system_code": "MES"},
    {"hostname": "mes-mcp01", "ip": "10.10.9.31", "port": 9000, "env": "PROD", "role": "MCP", "system_code": "MES"},
    {"hostname": "mes-dev01", "ip": "10.20.9.11", "port": 8080, "env": "DEV", "role": "API", "system_code": "MES"},
    {"hostname": "plan-app01", "ip": "10.10.10.11", "port": 443, "env": "PROD", "role": "Agent", "system_code": "PLAN"},
    {"hostname": "wms-batch01", "ip": "10.10.2.41", "port": 8080, "env": "PROD", "role": "Batch", "system_code": "WMS"},
    {"hostname": "wms-stg01", "ip": "10.30.2.21", "port": 8080, "env": "STAGE", "role": "API", "system_code": "WMS"},
    {"hostname": "erp-stg01", "ip": "10.30.1.11", "port": 8443, "env": "STAGE", "role": "WAS", "system_code": "ERP"},
    {"hostname": "crm-dev01", "ip": "10.20.3.11", "port": 8443, "env": "DEV", "role": "API", "system_code": "CRM"},
    {"hostname": "mes-batch01", "ip": "10.10.9.41", "port": 8080, "env": "PROD", "role": "Batch", "system_code": "MES"},
    {"hostname": "qms-was01", "ip": "10.10.11.11", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "QMS"},
    {"hostname": "qms-was02", "ip": "10.10.11.12", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "QMS"},
    {"hostname": "qms-dev01", "ip": "10.20.11.11", "port": 8443, "env": "DEV", "role": "WAS", "system_code": "QMS"},
    {"hostname": "plm-app01", "ip": "10.10.12.11", "port": 8080, "env": "PROD", "role": "API", "system_code": "PLM"},
    {"hostname": "plm-stg01", "ip": "10.30.12.11", "port": 8080, "env": "STAGE", "role": "API", "system_code": "PLM"},
    {"hostname": "irp-app01", "ip": "10.10.13.11", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "IRP"},
    {"hostname": "irp-mcp01", "ip": "10.10.13.31", "port": 9000, "env": "PROD", "role": "MCP", "system_code": "IRP"},
    {"hostname": "dcm-app01", "ip": "10.10.14.11", "port": 8443, "env": "PROD", "role": "WAS", "system_code": "DCM"},
    {"hostname": "dcm-mcp01", "ip": "10.10.14.31", "port": 9000, "env": "PROD", "role": "MCP", "system_code": "DCM"},
]

# API 마스터: API 등록 양식(업무정보 · 타입 · 리소스 · 레이아웃)에 그대로 대응
APIS = {
    "WMS-STOCK-HIS": {
        "system_code": "WMS", "name": "재고 이력 API", "version": "1.0.0", "description": "품목별 입출고 · 재고 변동 이력 조회",
        "business": {"category": "물류", "name": "재고 이력 관리", "program": "WMS_STK_HIS_010", "detail": "품목별 재고 변동 이력을 외부 시스템에 제공", "impact": "MEDIUM"},
        "direction": "SEND", "base_url": "https://wms.internal.example/api/v2", "auth_type": "OAuth2 Client Credentials", "content_type": "application/json", "timeout_ms": 5000,
        "operations": [
            {"method": "GET", "path": "/stock-history", "summary": "기간 · 창고별 재고 이력 목록"},
            {"method": "GET", "path": "/stock-history/{itemId}", "summary": "품목 재고 이력 상세"},
        ],
        "request_layout": [{"name": "itemId", "type": "string", "required": True, "description": "품목 코드"}, {"name": "from", "type": "string", "required": False, "description": "조회 시작일"}],
        "response_layout": [{"name": "itemId", "type": "string", "required": True, "description": "품목 코드"}, {"name": "items[].qty", "type": "integer", "required": False, "description": "변동 수량"}],
    },
    "WMS-OUTBOUND": {
        "system_code": "WMS", "name": "출고 관리 API", "version": "1.2.0", "description": "출고 요청 접수와 출고 상태 조회",
        "business": {"category": "물류", "name": "출고 관리", "program": "WMS_OUT_0102", "detail": "출고 요청 접수와 출고 상태 조회를 외부 시스템에 제공", "impact": "HIGH"},
        "direction": "SEND", "base_url": "https://wms.internal.example/api/v2", "auth_type": "OAuth2 Client Credentials", "content_type": "application/json", "timeout_ms": 5000,
        "operations": [
            {"method": "GET", "path": "/outbound-orders", "summary": "출고 요청 목록"},
            {"method": "GET", "path": "/outbound-orders/{orderId}", "summary": "출고 요청 상세"},
            {"method": "POST", "path": "/outbound-orders", "summary": "출고 요청 등록"},
        ],
        "request_layout": [{"name": "orderId", "type": "string", "required": True, "description": "출고 요청 번호"}],
        "response_layout": [{"name": "status", "type": "string", "required": True, "description": "출고 상태"}],
    },
    "ERP-ORDER": {
        "system_code": "ERP", "name": "주문 조회 API", "version": "2.0.0", "description": "주문 번호 · 기간으로 주문 내역 조회",
        "business": {"category": "재무", "name": "주문 조회", "program": "ERP_ORD_Q01", "detail": "주문 내역과 배송 현황 조회", "impact": "HIGH"},
        "direction": "SEND", "base_url": "https://erp.internal.example/api", "auth_type": "OAuth2 Client Credentials", "content_type": "application/json", "timeout_ms": 5000,
        "operations": [{"method": "GET", "path": "/orders", "summary": "기간별 주문 목록 조회"}, {"method": "GET", "path": "/orders/{orderId}", "summary": "주문 상세 조회"}],
        "request_layout": [], "response_layout": [],
    },
}

# MCP 서버 마스터: MCP 등록 양식(연결 정보 · Tool)에 대응
MCP_SERVERS = {
    ("MES", "품질 추적 MCP"): {
        "system_code": "MES", "name": "품질 추적 MCP", "description": "LOT 추적 · 품질 이슈 · 검사 결과 조회",
        "business": {"category": "생산", "name": "품질 추적", "program": "MES_QA_MCP", "detail": "생산 LOT의 자재 · 공정 이력과 품질 이슈를 AI Agent에 제공", "impact": "HIGH"},
        "transport": "STREAMABLE_HTTP", "endpoint": "https://mes.internal.example/mcp/quality", "auth_type": "OAuth2 Client Credentials", "host": "mes-mcp01", "protocol_version": "2025-06-18",
        "tools": [
            {"name": "get_lot_trace", "description": "LOT 번호로 자재 · 공정 이력 추적", "kind": "READ"},
            {"name": "list_quality_issues", "description": "기간별 품질 이슈 목록", "kind": "READ"},
            {"name": "hold_lot", "description": "LOT 출하 보류 처리", "kind": "WRITE"},
        ],
    },
    ("SCM", "입찰 관리 MCP"): {
        "system_code": "SCM", "name": "입찰 관리 MCP", "description": "구매 입찰 공고 · 응찰 현황 조회",
        "business": {"category": "구매", "name": "입찰 관리", "program": "SCM_BID_MCP", "detail": "입찰 공고와 응찰 현황을 구매 Agent에 제공", "impact": "MEDIUM"},
        "transport": "STREAMABLE_HTTP", "endpoint": "https://scm.internal.example/mcp/bids", "auth_type": "OAuth2 Client Credentials", "host": "scm-mcp01", "protocol_version": "2025-06-18",
        "tools": [{"name": "list_bids", "description": "진행 중인 입찰 목록", "kind": "READ"}, {"name": "get_bid", "description": "입찰 상세와 응찰 현황", "kind": "READ"}],
    },
}

CONTACTS = {
    "A2X 플랫폼팀": {"name": "A2X 운영 담당", "email": "a2x-help@example.com", "phone": "02-0000-1000", "channel": "#a2x-help"},
    "정보보안팀": {"name": "보안 담당", "email": "security@example.com", "phone": "02-0000-2000", "channel": "#security"},
    "물류시스템팀": {"name": "홍길동", "email": "hong@example.com", "phone": "02-0000-3100", "channel": "#wms"},
    "고객데이터팀": {"name": "정고객", "email": "jung.cust@example.com", "phone": "02-0000-3200", "channel": "#crm"},
    "스마트팩토리팀": {"name": "문생산", "email": "moon.mes@example.com", "phone": "02-0000-3300", "channel": "#mes"},
}
