// 샘플 페이지용 가짜 데이터. 백엔드 API가 생기면 TanStack Query 호출로 교체한다.
// 관리 단위는 시스템이다. Agent도 시스템으로 관리한다(SERVICE.md 부록 A).

export type Role = "일반 사용자" | "시스템 담당자" | "admin";
export const CURRENT_USER = "홍길동";

// 업무 프로세스 분류 (초안 — 실제 사내 프로세스 체계로 교체)
export const PROCESSES = ["영업", "판매", "구매", "생산", "물류", "재무", "인사", "고객서비스", "IT 공통"] as const;
export type Process = (typeof PROCESSES)[number];

export type SystemKind = "업무 시스템" | "AI Agent";

export type ServerInfo = {
  hostname: string;
  ip: string;
  port: string;
  env: "운영" | "개발" | "검증";
  role: string; // 용도: WAS, DB, MCP 등
};

export type System = {
  id: string;
  code: string;
  name: string;
  kind: SystemKind;
  process: Process;
  dept: string;
  managers: string[];
  url: string;
  dataLevel: "공개" | "사내 일반" | "대외비";
  description: string;
  servers: ServerInfo[];
};

const srv = (hostname: string, ip: string, port: string, role: string, env: ServerInfo["env"] = "운영"): ServerInfo => ({ hostname, ip, port, env, role });

export const systems: System[] = [
  { id: "SYS-ERP", code: "ERP", name: "ERP", kind: "업무 시스템", process: "재무", dept: "주문플랫폼팀", managers: ["이주문", "박정산"], url: "https://erp.internal.example", dataLevel: "대외비", description: "주문·정산 기간계",
    servers: [srv("erp-was01", "10.10.1.11", "8443", "WAS"), srv("erp-was02", "10.10.1.12", "8443", "WAS"), srv("erp-dev01", "10.20.1.11", "8443", "WAS", "개발")] },
  { id: "SYS-WMS", code: "WMS", name: "WMS", kind: "업무 시스템", process: "물류", dept: "물류시스템팀", managers: ["홍길동", "최물류"], url: "https://wms.internal.example", dataLevel: "사내 일반", description: "창고 재고·입출고 관리",
    servers: [srv("wms-api01", "10.10.2.21", "8080", "API"), srv("wms-mcp01", "10.10.2.31", "9000", "MCP")] },
  { id: "SYS-CRM", code: "CRM", name: "CRM", kind: "업무 시스템", process: "고객서비스", dept: "고객데이터팀", managers: ["정고객"], url: "https://crm.internal.example", dataLevel: "대외비", description: "고객 정보(개인정보 포함)",
    servers: [srv("crm-api01", "10.10.3.11", "8443", "API")] },
  { id: "SYS-HR", code: "HR", name: "HR", kind: "업무 시스템", process: "인사", dept: "인사시스템팀", managers: ["한인사"], url: "https://hr.internal.example", dataLevel: "대외비", description: "조직·인사 정보",
    servers: [srv("hr-mcp01", "10.10.4.31", "9000", "MCP")] },
  { id: "SYS-CSBOT", code: "CSBOT", name: "CSBOT", kind: "AI Agent", process: "고객서비스", dept: "고객지원팀", managers: ["홍길동", "윤상담"], url: "https://csbot.internal.example", dataLevel: "사내 일반", description: "고객 문의 응대 Agent",
    servers: [srv("csbot-app01", "10.10.5.11", "443", "Agent")] },
  { id: "SYS-PURCH", code: "PURCH", name: "PURCH", kind: "AI Agent", process: "구매", dept: "구매혁신팀", managers: ["강구매"], url: "https://purch-agent.internal.example", dataLevel: "사내 일반", description: "발주량 추천 Agent",
    servers: [srv("purch-dev01", "10.20.6.11", "443", "Agent", "개발")] },
  { id: "SYS-MKT", code: "MKT", name: "MKT", kind: "AI Agent", process: "영업", dept: "마케팅팀", managers: ["서마케"], url: "https://mkt-agent.internal.example", dataLevel: "사내 일반", description: "고객 세그먼트 분석 Agent",
    servers: [srv("mkt-app01", "10.10.7.11", "443", "Agent")] },
  { id: "SYS-SCM", code: "SCM", name: "SCM", kind: "업무 시스템", process: "구매", dept: "공급망혁신팀", managers: ["오공급", "남조달"], url: "https://scm.internal.example", dataLevel: "사내 일반", description: "발주 · 공급사 · 수요 예측 관리",
    servers: [srv("scm-was01", "10.10.8.11", "8443", "WAS"), srv("scm-was02", "10.10.8.12", "8443", "WAS"), srv("scm-mcp01", "10.10.8.31", "9000", "MCP"), srv("scm-stg01", "10.30.8.11", "8443", "WAS", "검증")] },
  { id: "SYS-MES", code: "MES", name: "MES", kind: "업무 시스템", process: "생산", dept: "스마트팩토리팀", managers: ["문생산", "배설비"], url: "https://mes.internal.example", dataLevel: "대외비", description: "작업지시 · 설비 · 생산 실적 관리",
    servers: [srv("mes-app01", "10.10.9.11", "8080", "API"), srv("mes-app02", "10.10.9.12", "8080", "API"), srv("mes-mcp01", "10.10.9.31", "9000", "MCP"), srv("mes-dev01", "10.20.9.11", "8080", "API", "개발")] },
  { id: "SYS-PLAN", code: "PLAN", name: "PLAN", kind: "AI Agent", process: "생산", dept: "생산기획팀", managers: ["박계획"], url: "https://plan-agent.internal.example", dataLevel: "사내 일반", description: "설비 상태와 작업지시를 보고 생산 계획을 제안하는 Agent",
    servers: [srv("plan-app01", "10.10.10.11", "443", "Agent")] },
];

export type AssetType = "API" | "MCP";
// 등록 진행상태: 저장 → 승인(admin 승인 대기) → 스테이지 → 운영
export type AssetStatus = "저장" | "승인 대기" | "스테이지" | "운영" | "반려" | "중지";
export const LIFECYCLE: { status: AssetStatus; label: string }[] = [
  { status: "저장", label: "저장" },
  { status: "승인 대기", label: "승인" },
  { status: "스테이지", label: "스테이지" },
  { status: "운영", label: "운영" },
];

// API 레이아웃(요청/응답 필드)
export type LayoutField = { name: string; type: string; required: boolean; description: string };

// API 신규 등록 상세 정보
export type ApiSpec = {
  version: string;
  business: {
    category: string; // 업무 분류
    name: string; // 업무명
    program: string; // 프로그램명
    detail: string; // 상세정보
    impact: "상" | "중" | "하"; // 업무영향도
  };
  direction: "송신" | "수신"; // 데이터 방향 (시스템 기준)
  baseUrl: string;
  auth: string;
  contentType: string;
  timeoutMs: number;
  requestLayout: LayoutField[];
  responseLayout: LayoutField[];
};
export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

// API의 오퍼레이션 (API→MCP 변환 시 Tool 하나로 바뀐다)
export type Operation = { method: HttpMethod; path: string; summary: string };

export type Tool = {
  name: string;
  description: string;
  kind: "조회" | "변경";
  source?: string; // API에서 변환된 Tool이면 원본 오퍼레이션 (예: "GET /customers/{id}")
};

// 타겟 시스템이 개발 · 운영하는 MCP 서버 등록 정보
export type McpSpec = {
  version: string;
  business: ApiSpec["business"];
  transport: "Streamable HTTP" | "SSE";
  endpoint: string;
  auth: string;
  host: string; // MCP 서버가 올라간 서버(시스템 서버 정보의 호스트명)
  protocolVersion: string;
  timeoutMs: number;
  hiddenTools: string[]; // 카탈로그에 공개하지 않는 Tool
};

// 카탈로그 대표 이미지: 준비된 아이콘 + 색, 또는 올린 이미지(data URL). 없으면 자동 아이콘
export type AssetIcon = { kind: "preset"; name: string; color: string } | { kind: "image"; src: string };

export type Asset = {
  id: string;
  icon?: AssetIcon;
  systemId: string;
  name: string;
  type: AssetType;
  status: AssetStatus;
  description: string;
  operations: Operation[]; // API만
  tools: Tool[]; // MCP만
  convertedFrom?: string; // API→MCP 변환으로 만든 MCP 서버면 원본 API 자산 ID
  api?: ApiSpec; // API 상세 (신규 등록 폼에서 입력)
  mcp?: McpSpec; // 타겟 시스템이 직접 개발한 MCP 서버 상세 (MCP 등록 폼에서 입력)
};

export const assets: Asset[] = [
  {
    id: "AS-001", icon: { kind: "preset", name: "cart", color: "#0071e3" }, systemId: "SYS-ERP", name: "주문 조회 API", type: "API", status: "운영", description: "주문 번호·기간으로 주문 내역 조회", tools: [],
    operations: [
      { method: "GET", path: "/orders", summary: "기간별 주문 목록 조회" },
      { method: "GET", path: "/orders/{orderId}", summary: "주문 상세 조회" },
      { method: "GET", path: "/orders/{orderId}/shipments", summary: "주문 배송 현황 조회" },
      { method: "POST", path: "/orders/{orderId}/cancel", summary: "주문 취소" },
    ],
  },
  {
    id: "AS-002", icon: { kind: "preset", name: "warehouse", color: "#6e4ff6" }, systemId: "SYS-WMS", name: "재고 MCP 서버", type: "MCP", status: "운영", description: "창고별 재고 조회·예약", operations: [],
    tools: [
      { name: "get_stock", description: "품목별 재고 조회", kind: "조회" },
      { name: "list_warehouses", description: "창고 목록 조회", kind: "조회" },
      { name: "reserve_stock", description: "재고 예약", kind: "변경" },
      { name: "cancel_reservation", description: "예약 취소", kind: "변경" },
    ],
  },
  {
    id: "AS-003", icon: { kind: "preset", name: "users", color: "#0071e3" }, systemId: "SYS-CRM", name: "고객 정보 API", type: "API", status: "운영", description: "고객 기본 정보 조회(개인정보 마스킹)", tools: [],
    operations: [
      { method: "GET", path: "/customers/{customerId}", summary: "고객 기본 정보 조회" },
      { method: "GET", path: "/customers/{customerId}/contacts", summary: "고객 연락 이력 조회" },
      { method: "GET", path: "/customers/search", summary: "고객 검색" },
    ],
  },
  {
    id: "AS-004", icon: { kind: "preset", name: "org", color: "#6e4ff6" }, systemId: "SYS-HR", name: "인사 조직도 MCP", type: "MCP", status: "운영", description: "조직·부서·결재선 조회", operations: [],
    tools: [
      { name: "get_org", description: "조직도 조회", kind: "조회" },
      { name: "find_employee", description: "임직원 검색", kind: "조회" },
      { name: "get_approval_line", description: "결재선 조회", kind: "조회" },
    ],
  },
  {
    id: "AS-005", icon: { kind: "preset", name: "truck", color: "#0071e3" }, systemId: "SYS-WMS", name: "입출고 API", type: "API", status: "운영", description: "입고·출고 내역 조회와 등록", tools: [],
    operations: [
      { method: "GET", path: "/inbounds", summary: "입고 내역 조회" },
      { method: "GET", path: "/outbounds", summary: "출고 내역 조회" },
      { method: "POST", path: "/outbounds", summary: "출고 요청 등록" },
    ],
  },
  {
    id: "AS-006", icon: { kind: "preset", name: "users", color: "#6e4ff6" }, systemId: "SYS-CRM", name: "고객 정보 MCP", type: "MCP", status: "운영", description: "고객 정보 API를 MCP Tool로 변환해 제공", operations: [], convertedFrom: "AS-003",
    tools: [
      { name: "get_customer", description: "고객 ID로 기본 정보를 조회한다(개인정보 마스킹)", kind: "조회", source: "GET /customers/{customerId}" },
      { name: "search_customers", description: "이름·전화번호 일부로 고객을 검색한다", kind: "조회", source: "GET /customers/search" },
    ],
  },
  // ---- SCM ----
  {
    id: "AS-007", icon: { kind: "preset", name: "receipt", color: "#0071e3" }, systemId: "SYS-SCM", name: "발주 관리 API", type: "API", status: "운영", description: "발주서 조회 · 등록 · 확정", tools: [],
    operations: [
      { method: "GET", path: "/purchase-orders", summary: "기간 · 공급사별 발주 목록 조회" },
      { method: "GET", path: "/purchase-orders/{poId}", summary: "발주 상세 조회" },
      { method: "POST", path: "/purchase-orders", summary: "발주 등록" },
      { method: "PUT", path: "/purchase-orders/{poId}/confirm", summary: "발주 확정" },
    ],
  },
  {
    id: "AS-008", icon: { kind: "preset", name: "building", color: "#6e4ff6" }, systemId: "SYS-SCM", name: "공급사 정보 MCP", type: "MCP", status: "운영", description: "공급사 검색 · 평가 등급 · 납기 이력", operations: [],
    tools: [
      { name: "search_suppliers", description: "품목 · 지역으로 공급사 검색", kind: "조회" },
      { name: "get_supplier", description: "공급사 기본 정보 조회", kind: "조회" },
      { name: "get_supplier_rating", description: "공급사 평가 등급 · 납기 준수율 조회", kind: "조회" },
    ],
  },
  {
    id: "AS-009", icon: { kind: "preset", name: "workflow", color: "#0071e3" }, systemId: "SYS-SCM", name: "수요 예측 API", type: "API", status: "스테이지", description: "품목별 4주 수요 예측값 제공(검증 중)", tools: [],
    operations: [
      { method: "GET", path: "/forecasts", summary: "품목군별 수요 예측 목록" },
      { method: "GET", path: "/forecasts/{itemId}", summary: "품목 수요 예측 상세" },
    ],
  },
  // ---- MES ----
  {
    id: "AS-010", icon: { kind: "preset", name: "doc", color: "#0071e3" }, systemId: "SYS-MES", name: "작업지시 API", type: "API", status: "운영", description: "작업지시 조회 · 생성 · 상태 변경", tools: [],
    operations: [
      { method: "GET", path: "/work-orders", summary: "라인 · 일자별 작업지시 목록" },
      { method: "GET", path: "/work-orders/{woId}", summary: "작업지시 상세" },
      { method: "POST", path: "/work-orders", summary: "작업지시 생성" },
      { method: "PUT", path: "/work-orders/{woId}/status", summary: "작업지시 상태 변경" },
    ],
  },
  {
    id: "AS-011", icon: { kind: "preset", name: "factory", color: "#6e4ff6" }, systemId: "SYS-MES", name: "설비 상태 MCP", type: "MCP", status: "운영", description: "설비 가동 상태 · 알람 · OEE", operations: [],
    tools: [
      { name: "get_equipment_status", description: "설비별 가동 · 정지 상태 조회", kind: "조회" },
      { name: "list_alarms", description: "최근 설비 알람 목록 조회", kind: "조회" },
      { name: "get_oee", description: "라인별 설비 종합 효율(OEE) 조회", kind: "조회" },
      { name: "reset_alarm", description: "확인된 알람 해제", kind: "변경" },
    ],
  },
  {
    id: "AS-012", icon: { kind: "preset", name: "factory", color: "#0071e3" }, systemId: "SYS-MES", name: "생산 실적 API", type: "API", status: "승인 대기", description: "LOT별 생산 실적 · 불량 수량", tools: [],
    operations: [
      { method: "GET", path: "/production-results", summary: "일자 · 라인별 생산 실적" },
      { method: "GET", path: "/production-results/{lotId}", summary: "LOT 실적 상세" },
    ],
  },
  // ---- 기존 시스템 추가 ----
  {
    id: "AS-013", icon: { kind: "preset", name: "card", color: "#0071e3" }, systemId: "SYS-ERP", name: "매출 정산 API", type: "API", status: "운영", description: "월별 매출 · 정산 결과 조회", tools: [],
    operations: [
      { method: "GET", path: "/settlements", summary: "월별 정산 목록" },
      { method: "GET", path: "/settlements/{month}", summary: "월 정산 상세" },
    ],
  },
  {
    id: "AS-014", icon: { kind: "preset", name: "doc", color: "#6e4ff6" }, systemId: "SYS-CRM", name: "상담 이력 MCP", type: "MCP", status: "운영", description: "고객 상담 이력 조회 · 요약 · 후속 조치 등록", operations: [],
    tools: [
      { name: "get_consult_history", description: "고객별 상담 이력 조회", kind: "조회" },
      { name: "summarize_case", description: "상담 건 요약 조회", kind: "조회" },
      { name: "create_followup", description: "후속 조치 등록", kind: "변경" },
    ],
  },
  {
    id: "AS-015", icon: { kind: "preset", name: "org", color: "#0071e3" }, systemId: "SYS-HR", name: "근태 조회 API", type: "API", status: "운영", description: "부서 · 개인 근태 현황 조회", tools: [],
    operations: [
      { method: "GET", path: "/attendance", summary: "부서별 근태 현황" },
      { method: "GET", path: "/attendance/{employeeId}", summary: "개인 근태 상세" },
    ],
  },
];

export type ReqStatus = "승인 대기" | "승인" | "반려" | "해지";

// 1단계: 시스템 구독 (구독 시스템 → 대상 시스템의 MCP 서버/API). 승인권자: 대상 시스템 담당자
export type SystemSub = {
  id: string;
  fromSystemId: string;
  assetId: string;
  purpose: string;
  requestedBy: string;
  requestedAt: string;
  status: ReqStatus;
};

export const systemSubs: SystemSub[] = [
  { id: "SB-104", fromSystemId: "SYS-CSBOT", assetId: "AS-001", purpose: "고객 문의 시 주문 상태 안내", requestedBy: "윤상담", requestedAt: "2026-11-23", status: "승인 대기" },
  { id: "SB-103", fromSystemId: "SYS-PURCH", assetId: "AS-002", purpose: "발주 추천 시 재고 확인", requestedBy: "강구매", requestedAt: "2026-11-22", status: "승인 대기" },
  { id: "SB-101", fromSystemId: "SYS-CSBOT", assetId: "AS-002", purpose: "배송 문의 시 재고 확인", requestedBy: "홍길동", requestedAt: "2026-11-20", status: "승인" },
  { id: "SB-100", fromSystemId: "SYS-CSBOT", assetId: "AS-004", purpose: "담당 부서 안내", requestedBy: "홍길동", requestedAt: "2026-11-19", status: "승인" },
  { id: "SB-099", fromSystemId: "SYS-MKT", assetId: "AS-003", purpose: "세그먼트 분석", requestedBy: "서마케", requestedAt: "2026-11-18", status: "승인" },
  { id: "SB-102", fromSystemId: "SYS-CSBOT", assetId: "AS-005", purpose: "배송 문의 시 출고 현황 확인", requestedBy: "홍길동", requestedAt: "2026-11-21", status: "승인" },
  { id: "SB-096", fromSystemId: "SYS-PURCH", assetId: "AS-001", purpose: "주문량 기반 발주 추천", requestedBy: "강구매", requestedAt: "2026-11-14", status: "승인" },
  { id: "SB-098", fromSystemId: "SYS-CSBOT", assetId: "AS-006", purpose: "문의 고객 확인", requestedBy: "홍길동", requestedAt: "2026-11-17", status: "승인" },
  { id: "SB-095", fromSystemId: "SYS-MKT", assetId: "AS-002", purpose: "재고 연계 프로모션", requestedBy: "서마케", requestedAt: "2026-11-12", status: "반려" },
  { id: "SB-094", fromSystemId: "SYS-PURCH", assetId: "AS-007", purpose: "추천 발주안 등록", requestedBy: "강구매", requestedAt: "2026-11-11", status: "승인" },
  { id: "SB-093", fromSystemId: "SYS-PURCH", assetId: "AS-008", purpose: "대체 공급사 추천", requestedBy: "강구매", requestedAt: "2026-11-11", status: "승인" },
  { id: "SB-092", fromSystemId: "SYS-PLAN", assetId: "AS-011", purpose: "설비 상태 기반 생산 계획", requestedBy: "박계획", requestedAt: "2026-11-10", status: "승인" },
  { id: "SB-091", fromSystemId: "SYS-PLAN", assetId: "AS-010", purpose: "작업지시 현황 반영", requestedBy: "박계획", requestedAt: "2026-11-23", status: "승인 대기" },
  { id: "SB-090", fromSystemId: "SYS-CSBOT", assetId: "AS-014", purpose: "상담 이력 기반 응대", requestedBy: "홍길동", requestedAt: "2026-11-09", status: "승인" },
  { id: "SB-089", fromSystemId: "SYS-MKT", assetId: "AS-013", purpose: "캠페인 매출 효과 분석", requestedBy: "서마케", requestedAt: "2026-11-08", status: "승인" },
];

// 2단계: 사용자 Tool 사용 신청 (승인된 MCP 시스템 구독 안에서). 승인권자: 대상 시스템 담당자
export type ToolRequest = {
  id: string;
  user: string;
  subId: string;
  tool: string;
  purpose: string;
  requestedAt: string;
  status: ReqStatus;
};

export const toolRequests: ToolRequest[] = [
  { id: "TR-210", user: "김민수", subId: "SB-101", tool: "reserve_stock", purpose: "상담 중 재고 선점", requestedAt: "2026-11-24", status: "승인 대기" },
  { id: "TR-209", user: "홍길동", subId: "SB-100", tool: "get_approval_line", purpose: "결재선 안내", requestedAt: "2026-11-24", status: "승인 대기" },
  { id: "TR-205", user: "홍길동", subId: "SB-101", tool: "get_stock", purpose: "재고 확인", requestedAt: "2026-11-21", status: "승인" },
  { id: "TR-204", user: "이영희", subId: "SB-101", tool: "get_stock", purpose: "재고 확인", requestedAt: "2026-11-21", status: "승인" },
  { id: "TR-201", user: "홍길동", subId: "SB-100", tool: "get_org", purpose: "담당 부서 안내", requestedAt: "2026-11-19", status: "승인" },
  { id: "TR-199", user: "강구매", subId: "SB-093", tool: "search_suppliers", purpose: "대체 공급사 탐색", requestedAt: "2026-11-12", status: "승인" },
  { id: "TR-198", user: "강구매", subId: "SB-093", tool: "get_supplier_rating", purpose: "공급사 평가 확인", requestedAt: "2026-11-12", status: "승인" },
  { id: "TR-197", user: "박계획", subId: "SB-092", tool: "get_equipment_status", purpose: "가동 설비 확인", requestedAt: "2026-11-11", status: "승인" },
  { id: "TR-196", user: "박계획", subId: "SB-092", tool: "get_oee", purpose: "라인 효율 확인", requestedAt: "2026-11-11", status: "승인" },
  { id: "TR-195", user: "정현장", subId: "SB-092", tool: "reset_alarm", purpose: "현장 알람 처리", requestedAt: "2026-11-22", status: "승인 대기" },
  { id: "TR-194", user: "홍길동", subId: "SB-090", tool: "get_consult_history", purpose: "이전 상담 확인", requestedAt: "2026-11-10", status: "승인" },
  { id: "TR-193", user: "김민수", subId: "SB-090", tool: "summarize_case", purpose: "상담 요약", requestedAt: "2026-11-10", status: "승인" },
  { id: "TR-192", user: "홍길동", subId: "SB-090", tool: "create_followup", purpose: "후속 조치 등록", requestedAt: "2026-11-23", status: "승인 대기" },
];

