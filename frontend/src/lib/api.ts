// 백엔드 API 호출. 개발 중에는 Vite 프록시가 /api를 FastAPI(8000)로 넘기므로 같은 출처 쿠키로 인증된다.

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // 서비스 오류는 {detail, code}, 입력 검증 오류는 {detail: [...]}
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join(".") ?? ""} ${d.msg}`).join(", ")
      : data.detail ?? `요청 실패 (${res.status})`;
    throw new ApiError(res.status, data.code ?? "error", detail);
  }
  return data as T;
}

export const get = <T>(path: string) => api<T>("GET", path);
export const post = <T>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const put = <T>(path: string, body?: unknown) => api<T>("PUT", path, body);
export const patch = <T>(path: string, body?: unknown) => api<T>("PATCH", path, body);
export const del = <T>(path: string) => api<T>("DELETE", path);

export function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "" && v !== false) s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
}

// ---------- 응답 타입 (백엔드 스키마와 같다) ----------

export type Health = { status: string; service: string; version: string };
export type UserBrief = { id: number; name: string; email: string };
export type UserOut = UserBrief & { role: string; auth_provider: string };
export type EffectiveRole = "USER" | "MANAGER" | "ADMIN"; // 화면 역할: ADMIN은 저장, MANAGER는 담당 시스템 유무로 계산
export type StoredRole = "USER" | "ADMIN";
export type Me = { user: UserOut; effective_role: EffectiveRole; managed_system_ids: number[] };
export type SessionOut = { user: UserOut; effective_role: EffectiveRole; token: string };

export type SystemKind = "BUSINESS" | "AGENT";
export type ServerEnv = "PROD" | "STAGE" | "DEV";
export type DataLevel = "PUBLIC" | "INTERNAL" | "CONFIDENTIAL";
export type ServerOut = { id: number; system_id: number; hostname: string; ip: string; port: number; env: ServerEnv; role: string };
export type ServerRow = ServerOut & { system_code: string; system_name: string; process: string };
export type SystemOut = {
  id: number;
  code: string;
  name: string;
  kind: SystemKind;
  process: string;
  dept: string;
  url: string;
  data_level: DataLevel;
  description: string;
  managers: UserBrief[];
  servers: ServerOut[];
};
export type SystemBrief = { id: number; code: string; name: string; dept: string; kind: SystemKind };

export type AssetType = "API" | "MCP";
export type AssetSource = "API" | "MCP_DIRECT" | "MCP_CONVERTED";
export type AssetStatus = "DRAFT" | "PENDING" | "STAGE" | "LIVE" | "REJECTED" | "SUSPENDED";
export type ToolKind = "READ" | "WRITE";
export type Impact = "HIGH" | "MEDIUM" | "LOW";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type IconOut = { kind: string; name: string | null; color: string | null };
export type Business = { category: string; name: string; program: string; detail: string; impact: Impact };
export type OperationOut = { id: number; method: HttpMethod; path: string; summary: string };
export type LayoutField = { name: string; type: string; required: boolean; description: string };
export type ToolOut = { id: number; name: string; description: string; kind: ToolKind; exposed: boolean; source_operation_id: number | null };

export type AssetSummary = {
  id: number;
  type: AssetType;
  source: AssetSource;
  status: AssetStatus;
  name: string;
  version: string;
  description: string;
  system: SystemBrief;
  icon: IconOut | null;
  operation_count: number;
  tool_count: number;
  subscriber_count: number;
  converted_from_id: number | null;
  updated_at: string | null;
};
export type AssetDetail = AssetSummary & {
  business: Business;
  direction: "SEND" | "RECEIVE" | null;
  base_url: string | null;
  auth_type: string | null;
  content_type: string | null;
  timeout_ms: number | null;
  operations: OperationOut[];
  request_layout: LayoutField[];
  response_layout: LayoutField[];
  transport: "STREAMABLE_HTTP" | "SSE" | null;
  endpoint: string | null;
  protocol_version: string | null;
  host_server_id: number | null;
  tools: ToolOut[];
};

export type ReqStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
export type AssetRef = { id: number; name: string; type: AssetType };
export type SubscriptionOut = {
  id: number;
  status: ReqStatus;
  purpose: string;
  client_system: SystemBrief;
  provider_system: SystemBrief;
  asset: AssetRef;
  requested_by: UserBrief | null;
  created_at: string | null;
  decided_at: string | null;
  decision_note: string;
  can_decide: boolean;
  can_cancel: boolean;
};
export type ToolRef = { id: number; name: string; kind: ToolKind; description: string };
export type ToolRequestOut = {
  id: number;
  status: ReqStatus;
  purpose: string;
  user: UserBrief;
  tool: ToolRef;
  subscription_id: number;
  client_system: SystemBrief;
  provider_system: SystemBrief;
  asset: AssetRef;
  created_at: string | null;
  decided_at: string | null;
  decision_note: string;
  can_decide: boolean;
  can_cancel: boolean;
};
export type ConnectionOut = {
  subscription_id: number;
  client_system: SystemBrief;
  provider_system: SystemBrief;
  asset: AssetRef;
  tools: (ToolRef & { my_status: ReqStatus | null })[];
};
export type ToolSuggestion = { operation_id: number; method: HttpMethod; path: string; tool_name: string; description: string; kind: ToolKind; input_schema: Record<string, unknown> };

// ---------- 개별 호출 ----------

export type LayoutFieldDto = LayoutField;

// xlsx 레이아웃을 백엔드(openpyxl)에서 파싱한다. 파일은 원본 바이트로 보낸다.
export async function parseExcelLayout(file: File): Promise<LayoutFieldDto[]> {
  const res = await fetch(`${BASE}/layout/excel`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `엑셀 파싱 실패 (${res.status})`);
  return body.fields;
}

export const fetchHealth = () => get<Health>("/health");

// ---------- A2X Agent 채팅 (POST /agent/chat) ----------

export type AgentRoute = "consult" | "automation" | "devsupport" | "error" | "guard";
export type FormKind = "api" | "mcp" | "subscription" | "system" | "server" | "system_servers";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type FormSuggestion = { form: FormKind; values: Record<string, any>; source?: { label?: string }; notes: string[] };
export type AgentAction = { type: "ask" | "open" | "request"; label: string; message?: string; page?: string; tx_id?: string; asset_id?: string };
export type AgentSource = { no?: number; doc?: string; section?: string; excerpt?: string; label?: string; type?: string; tx_id?: string };
// 실행 흐름 한 단계(시퀀스 다이어그램의 화살표 하나): src가 dst에게 label을 보냈고 결과가 detail
export type TraceStep = { seq: number; src: string; dst: string; label: string; detail: string; ok: boolean; ms: number | null };
export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ChatContext = { page?: string; asset_id?: number; transaction_id?: string };
export type ChatResponse = {
  route: AgentRoute;
  rule: string;
  answer: string;
  sources: AgentSource[];
  form_suggestion: FormSuggestion | null;
  actions: AgentAction[];
  used_llm: string | null;
  guard_notes: string[];
  trace: TraceStep[];
};

export const agentChat = (message: string, context: ChatContext, history: ChatTurn[]) =>
  post<ChatResponse>("/agent/chat", { message, context, history });

// ---------- 모니터링 (GET /monitoring/*) ----------

export type SystemRef = { id: number | null; code: string; name: string };
export type CallRow = {
  tx_id: string;
  kind: "API" | "MCP";
  success: boolean;
  return_code: string;
  name: string; // API 이름, MCP는 "서버 · Tool"
  client_system: SystemRef;
  provider_system: SystemRef;
  user: string | null;
  user_login?: string | null; // 호출 사용자 로그인 ID(이메일)
  subscription_id: number | null;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  client_ip: string;
  protocol: string;
  method: string;
  uri: string;
  error_message: string;
};
export type CallPage = { items: CallRow[]; total: number; page: number; size: number };
export type Stage = { name: string; ms: number; ok: boolean };
export type CallDetail = CallRow & {
  request_headers: Record<string, string> | null;
  request_body: unknown;
  response_body: unknown;
  stages: Stage[];
  classification: { category: string; side: string; action: string } | null;
};
export type StatRow = { key: string; label: string; api: number; mcp: number; errors: number; avg_ms: number };
// 인스턴스 모니터링(/monitoring/instances)
export type InstanceStatus = "ok" | "warn" | "down" | "off";
export type InstanceComponent = { key: string; name: string; status: InstanceStatus; detail: string; kind: string; latency_ms: number | null; endpoint: string; metrics: Record<string, unknown> };
export type InstanceGroup = { key: string; label: string; desc: string; status: InstanceStatus; components: InstanceComponent[] };
export type Instances = {
  checked_at: string;
  status: InstanceStatus;
  counts: Record<InstanceStatus, number>;
  host: { name: string; os: string; python: string };
  groups: InstanceGroup[];
};

export type MonitoringSummary = {
  today_calls: number;
  today_errors: number;
  today_error_rate: number;
  failed_24h: number;
  recent_errors: { name: string; code: string; category: string; count: number }[];
};

// ---------- 컨설팅 문서 (admin, /consult-docs) ----------

export type DocStatus = "INDEXING" | "INDEXED" | "FAILED";
export type ConsultDocOut = {
  id: number;
  name: string;
  status: DocStatus;
  chunk_count: number;
  size_bytes: number;
  error: string;
  uploaded_by: string | null;
  created_at: string;
  is_sample: boolean;
};
export type DocSearchOut = {
  ok: boolean;
  top_score: number;
  coverage: number;
  keywords: string[];
  missing: string[];
  hits: { doc: string; section: string; score: number; excerpt: string }[];
};

// 파일은 multipart 대신 원본 바이트로 보낸다(레이아웃 엑셀과 같은 방식)
export async function uploadConsultDoc(file: File): Promise<ConsultDocOut> {
  const res = await fetch(`${BASE}/consult-docs?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.code ?? "error", typeof body.detail === "string" ? body.detail : `업로드 실패 (${res.status})`);
  return body as ConsultDocOut;
}
