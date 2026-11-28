import { useState } from "react";
import { Check, Eye, EyeOff, FileJson, Loader2, Plug, Plus, Sparkles, Trash2 } from "lucide-react";
import { PROCESSES, type AssetIcon, type McpSpec, type Role, type Tool } from "@/lib/sample-data";
import { get, post, put, type AssetDetail, type AssetStatus, type FormSuggestion } from "@/lib/api";
import { useAgentBridge, useEditRequest, useSuggestion } from "@/lib/agent-bridge";
import { AgentFilledNote } from "@/components/agent-filled";
import { ASSET_STATUS, DATA_LEVEL, LIFECYCLE_STEPS, SERVER_ENV } from "@/lib/labels";
import { useAction, useSystems } from "@/lib/queries";
import { ErrorNote } from "@/components/feedback";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/tabs";
import { AssetIconPicker, toIconIn, normalizeIcon } from "@/components/asset-icon";
import { Lbl, ReadOnly, Section, textareaCls } from "@/pages/api-register";
import { cn } from "@/lib/utils";

// 타겟 시스템이 직접 개발 · 운영하는 MCP 서버를 A2X에 등록한다.
// (A2X가 API를 변환해 만드는 MCP는 'MCP 변환' 메뉴)

type ToolRow = Tool & { exposed: boolean; params: number };
type ToolSource = "test" | "json" | "manual";

const READ_PREFIX = /^(get|list|search|find|query|read|describe|summarize)_/;

// tools/list 응답(JSON) → Tool 목록. 조회/변경은 readOnlyHint 우선, 없으면 이름 규칙으로 판정
export function parseToolsList(text: string): ToolRow[] {
  const doc = JSON.parse(text);
  const list = Array.isArray(doc) ? doc : doc?.result?.tools ?? doc?.tools;
  if (!Array.isArray(list)) throw new Error("tools 배열을 찾지 못했습니다. tools/list 응답 형식인지 확인하세요.");
  return list.map((t: { name: string; description?: string; inputSchema?: { properties?: object }; annotations?: { readOnlyHint?: boolean } }) => {
    const ro = t.annotations?.readOnlyHint ?? READ_PREFIX.test(t.name);
    return {
      name: String(t.name),
      description: t.description ?? "",
      kind: ro ? "조회" : "변경",
      exposed: true,
      params: Object.keys(t.inputSchema?.properties ?? {}).length,
    };
  });
}

// 연결 테스트 샘플 응답 (실제로는 백엔드가 엔드포인트에 initialize → tools/list를 호출)
const SAMPLE_TOOLS_LIST = JSON.stringify(
  {
    jsonrpc: "2.0",
    id: 1,
    result: {
      tools: [
        { name: "get_lot_trace", description: "LOT 번호로 자재 · 공정 이력 추적", inputSchema: { type: "object", properties: { lotId: { type: "string" } } }, annotations: { readOnlyHint: true } },
        { name: "list_quality_issues", description: "기간별 품질 이슈 목록", inputSchema: { type: "object", properties: { from: { type: "string" }, to: { type: "string" } } }, annotations: { readOnlyHint: true } },
        { name: "get_inspection_result", description: "검사 결과 상세 조회", inputSchema: { type: "object", properties: { inspectionId: { type: "string" } } } },
        { name: "hold_lot", description: "LOT 출하 보류 처리", inputSchema: { type: "object", properties: { lotId: { type: "string" }, reason: { type: "string" } } }, annotations: { readOnlyHint: false } },
      ],
    },
  },
  null,
  2,
);

export function McpRegisterPage({ role }: { role: Role }) {
  const mySystems = useSystems({ mine: role !== "admin", kind: "BUSINESS" }).data ?? [];
  const [pickedSystem, setSystemId] = useState<number | null>(null);
  const systemId = pickedSystem ?? mySystems[0]?.id ?? 0;
  const sys = mySystems.find((s) => s.id === systemId);

  const [savedId, setSavedId] = useState<number | undefined>();
  const [status, setStatus] = useState<AssetStatus | undefined>();
  // 승인 이후(스테이지 · 운영 · 중지)에 고쳐 저장하면 다시 승인 대기로 돌아간다(재승인)
  const approved = status === "STAGE" || status === "LIVE" || status === "SUSPENDED";
  const pending = status === "PENDING";

  const [basic, setBasic] = useState({ name: "", version: "1.0.0", description: "" });
  const [icon, setIcon] = useState<AssetIcon | undefined>();
  const [business, setBusiness] = useState<McpSpec["business"]>({ category: sys?.process ?? PROCESSES[0], name: "", program: "", detail: "", impact: "중" });
  const [conn, setConn] = useState({
    transport: "Streamable HTTP" as McpSpec["transport"],
    endpoint: "",
    auth: "OAuth2 Client Credentials",
    host: "",
    protocolVersion: "2025-06-18",
    timeoutMs: 10000,
  });
  const [tools, setTools] = useState<ToolRow[]>([]);
  const [source, setSource] = useState<ToolSource>("test");
  const [jsonText, setJsonText] = useState("");
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const mcpHosts = sys?.servers ?? [];

  // ---- Tool 불러오기 ----
  const runTest = () => {
    setMsg(null);
    if (!/^https?:\/\//.test(conn.endpoint)) return setMsg({ ok: false, text: "엔드포인트 URL(https://…)을 먼저 입력하세요." });
    setTesting(true);
    setTimeout(() => {
      const rows = parseToolsList(SAMPLE_TOOLS_LIST);
      setTools(rows);
      setTesting(false);
      setMsg({ ok: true, text: `연결 성공 · MCP ${conn.protocolVersion} · ${conn.transport} · Tool ${rows.length}개를 불러왔습니다. (샘플 응답)` });
    }, 900);
  };
  const applyJson = () => {
    try {
      const rows = parseToolsList(jsonText);
      setTools(rows);
      setMsg({ ok: true, text: `Tool ${rows.length}개를 가져왔습니다.` });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof SyntaxError ? "JSON 형식이 올바르지 않습니다." : (e as Error).message });
    }
  };
  const upd = (i: number, patch: Partial<ToolRow>) => setTools((t) => t.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  // ---- Agent 자동 채움: 패널의 '양식에 채우기' 또는 아래 버튼(Agent에게 요청) ----
  const bridge = useAgentBridge();
  const [agentFilled, setAgentFilled] = useState<FormSuggestion | null>(null);
  // Agent 제안과 저장된 MCP 서버 불러오기가 같은 값 형식(AssetDetail)을 쓴다
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fill = (v: Record<string, any>) => {
    const IMPACT_LABEL = { HIGH: "상", MEDIUM: "중", LOW: "하" } as const;
    if (v.system_id) setSystemId(v.system_id);
    const target = mySystems.find((x) => x.id === v.system_id) ?? sys;
    if (v.name) setBasic({ name: v.name, version: v.version ?? "1.0.0", description: v.description ?? "" });
    if (v.business) {
      const b = v.business;
      setBusiness({ category: b.category || business.category, name: b.name ?? "", program: b.program ?? "", detail: b.detail ?? "", impact: IMPACT_LABEL[b.impact as keyof typeof IMPACT_LABEL] ?? "중" });
    }
    if (v.endpoint !== undefined)
      setConn({
        transport: v.transport === "SSE" ? "SSE" : "Streamable HTTP",
        endpoint: v.endpoint ?? "",
        auth: v.auth_type || conn.auth,
        host: target?.servers.find((h) => h.id === v.host_server_id)?.hostname ?? "",
        protocolVersion: v.protocol_version ?? "2025-06-18",
        timeoutMs: v.timeout_ms ?? 10000,
      });
    if (v.tools?.length)
      setTools(
        (v.tools as { name: string; description: string; kind: string; exposed: boolean }[]).map((t) => ({
          name: t.name, description: t.description ?? "", kind: t.kind === "WRITE" ? "변경" : "조회", exposed: t.exposed ?? true, params: 0,
        }) as ToolRow),
      );
  };
  useSuggestion("mcp", (s) => {
    fill(s.values);
    setAgentFilled(s);
  });
  // 카탈로그 '수정': 저장된 MCP 서버를 불러와 같은 양식에서 고친다
  const [loadError, setLoadError] = useState<unknown>(null);
  useEditRequest("MCP", (id) => {
    setLoadError(null);
    get<AssetDetail>(`/assets/${id}`)
      .then((d) => {
        fill(d);
        setIcon(normalizeIcon(d.icon));
        setSavedId(d.id);
        setStatus(d.status);
        setAgentFilled(null);
      })
      .catch(setLoadError);
  });
  const askAgent = () => bridge.ask(`${sys?.code ?? ""} ${basic.name} MCP 등록 채워줘`.replace(/\s+/g, " ").trim());

  // ---- 저장 / 승인 요청 ----
  const IMPACT_CODE = { 상: "HIGH", 중: "MEDIUM", 하: "LOW" } as const;
  const payload = (submit: boolean) => ({
    system_id: systemId,
    name: basic.name,
    version: basic.version,
    description: basic.description,
    icon: toIconIn(icon),
    business: { ...business, impact: IMPACT_CODE[business.impact] },
    transport: conn.transport === "SSE" ? "SSE" : "STREAMABLE_HTTP",
    endpoint: conn.endpoint,
    auth_type: conn.auth,
    host_server_id: mcpHosts.find((h) => h.hostname === conn.host)?.id ?? null,
    protocol_version: conn.protocolVersion,
    timeout_ms: conn.timeoutMs,
    // 숨긴 Tool도 함께 저장한다(카탈로그에는 공개 Tool만 노출)
    tools: tools.filter((t) => t.name).map(({ name, description, kind, exposed }) => ({ name, description, kind: kind === "변경" ? "WRITE" : "READ", exposed })),
    submit,
  });
  const saveMut = useAction((submit: boolean) =>
    savedId ? put<AssetDetail>(`/assets/${savedId}/mcp`, payload(submit)) : post<AssetDetail>("/assets/mcp", payload(submit)),
  );
  const save = (next: "DRAFT" | "PENDING") =>
    saveMut.mutate(next === "PENDING", {
      onSuccess: (a) => {
        setSavedId(a.id);
        setStatus(a.status);
        setAgentFilled(null);
      },
    });
  const exposedCount = tools.filter((t) => t.exposed).length;
  const canSave = !!systemId && !!basic.name && !saveMut.isPending;
  const canRequest = canSave && !!conn.endpoint && exposedCount > 0 && !!business.name;
  const currentStep = status ? LIFECYCLE_STEPS.findIndex((s) => s.status === status) : -1;

  return (
    <div className="max-w-5xl space-y-4">
      {/* 진행상태 */}
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div className="flex items-center gap-2">
            {LIFECYCLE_STEPS.map((s, i) => (
              <div key={s.status} className="flex items-center gap-2">
                <div
                  className={cn(
                    "flex items-center gap-1.5 rounded-full px-3 py-1 text-sm ring-1",
                    i < currentStep && "bg-[#ecf9ef] text-[#1e6b34] ring-[#c4ebcf]",
                    i === currentStep && "bg-accent font-bold text-[#0058b9] ring-primary",
                    i > currentStep && "text-muted-foreground ring-black/[0.08]",
                  )}
                >
                  {i < currentStep ? <Check className="size-3.5" /> : <span className="text-xs">{i + 1}</span>}
                  {s.label}
                </div>
                {i < LIFECYCLE_STEPS.length - 1 && <span className="h-px w-6 bg-black/10" />}
              </div>
            ))}
            {status === "REJECTED" && <Badge variant="danger">반려됨 — 수정 후 다시 요청</Badge>}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={askAgent} title="외부 마스터(MCP 서버 마스터)에서 읽어 채울 값을 Agent가 제안합니다">
              <Sparkles /> Agent로 채우기
            </Button>
            {approved ? (
              <Button onClick={() => confirm(`승인된 MCP 서버를 고치면 다시 승인 대기로 돌아가고, 재승인 · 운영 전환 전까지 호출할 수 없습니다. 저장할까요?`) && save("PENDING")} disabled={!canRequest}>
                수정 후 재승인 요청
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => save("DRAFT")} disabled={!canSave}>저장</Button>
                <Button onClick={() => save("PENDING")} disabled={!canRequest || pending}>승인 요청</Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
      {savedId && (pending || approved) && (
        <p className="text-sm text-muted-foreground">
          {pending
            ? "admin 승인 대기 중입니다. 고쳐서 저장하면 승인 대기 상태로 내용만 바뀝니다. (구독 · 승인 > API · MCP 등록 승인)"
            : `현재 ${ASSET_STATUS[status!]} 상태입니다. 고쳐서 저장하면 다시 승인을 받아야 합니다(구독 · Tool 권한은 그대로 유지).`}
        </p>
      )}
      <ErrorNote error={loadError} />

      {agentFilled && <AgentFilledNote s={agentFilled} onClose={() => setAgentFilled(null)} />}

      <fieldset className="space-y-4">
        {/* 1. 시스템 정보 */}
        <Section hl={!!agentFilled} no={1} title="시스템 정보" desc="MCP 서버를 개발 · 운영하는 타겟 시스템. 시스템 마스터에서 가져옵니다.">
          <div className="grid gap-4 sm:grid-cols-3">
            <Lbl label="시스템">
              <NativeSelect value={systemId} disabled={!!savedId} onChange={(e) => { setSystemId(Number(e.target.value)); setConn((c) => ({ ...c, host: "" })); }}>
                {mySystems.map((s) => <option key={s.id} value={s.id}>{s.code !== s.name ? `${s.name} (${s.code})` : s.name}</option>)}
              </NativeSelect>
            </Lbl>
            <ReadOnly label="업무 프로세스" value={sys?.process} />
            <ReadOnly label="소속 부서" value={sys?.dept} />
            <ReadOnly label="담당자" value={sys?.managers.map((m) => m.name).join(", ")} />
            <ReadOnly label="데이터 등급" value={sys && DATA_LEVEL[sys.data_level]} />
            <ReadOnly label="서비스 URL" value={sys?.url} />
          </div>
        </Section>

        {/* 2. 기본정보 */}
        <Section hl={!!agentFilled} no={2} title="기본정보">
          <div className="grid gap-4 sm:grid-cols-3">
            <Lbl label="MCP 서버 이름"><Input value={basic.name} onChange={(e) => setBasic({ ...basic, name: e.target.value })} /></Lbl>
            <Lbl label="버전"><Input value={basic.version} onChange={(e) => setBasic({ ...basic, version: e.target.value })} /></Lbl>
            <ReadOnly label="등록 진행상태" value={status ? ASSET_STATUS[status] : "작성 중 (미저장)"} />
            <Lbl label="설명" className="sm:col-span-3"><Input value={basic.description} onChange={(e) => setBasic({ ...basic, description: e.target.value })} /></Lbl>
            <div className="space-y-1.5 text-sm sm:col-span-3">
              <span className="font-medium">카탈로그 대표 이미지</span>
              <AssetIconPicker value={icon} onChange={setIcon} fallback={{ type: "MCP", systemId }} />
            </div>
          </div>
        </Section>

        {/* 3. 업무정보 */}
        <Section hl={!!agentFilled} no={3} title="업무정보">
          <div className="grid gap-4 sm:grid-cols-3">
            <Lbl label="업무 분류">
              <NativeSelect value={business.category} onChange={(e) => setBusiness({ ...business, category: e.target.value })}>
                {PROCESSES.map((p) => <option key={p}>{p}</option>)}
              </NativeSelect>
            </Lbl>
            <Lbl label="업무명"><Input value={business.name} onChange={(e) => setBusiness({ ...business, name: e.target.value })} /></Lbl>
            <Lbl label="프로그램명"><Input className="font-mono" value={business.program} onChange={(e) => setBusiness({ ...business, program: e.target.value })} /></Lbl>
            <Lbl label="상세정보" className="sm:col-span-2">
              <textarea rows={2} className={textareaCls} value={business.detail} onChange={(e) => setBusiness({ ...business, detail: e.target.value })} />
            </Lbl>
            <div className="space-y-1.5 text-sm">
              <span className="font-medium">업무영향도</span>
              <div className="flex gap-2">
                {(["상", "중", "하"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setBusiness({ ...business, impact: v })}
                    className={cn("flex-1 rounded-xl py-2 ring-1", business.impact === v ? (v === "상" ? "bg-[#fdecee] text-[#d70015] ring-[#ffc2c8]" : "bg-accent ring-primary") : "ring-black/[0.08] hover:bg-[#f5f6f8]")}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* 4. 연결 정보 */}
        <Section hl={!!agentFilled} no={4} title="연결 정보" desc="A2X Gateway가 이 MCP 서버에 접속할 때 쓰는 정보입니다.">
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="space-y-1.5 text-sm sm:col-span-2">
              <span className="font-medium">전송 방식</span>
              <div className="flex gap-2">
                {(["Streamable HTTP", "SSE"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setConn({ ...conn, transport: v })}
                    className={cn("flex-1 rounded-xl px-3 py-2 text-left ring-1", conn.transport === v ? "bg-accent ring-primary" : "ring-black/[0.08] hover:bg-[#f5f6f8]")}
                  >
                    <span className="block font-bold">{v}</span>
                    <span className="text-[11.5px] text-muted-foreground">{v === "SSE" ? "이전 방식 (호환용)" : "권장 · 원격 MCP 표준"}</span>
                  </button>
                ))}
              </div>
            </div>
            <Lbl label="프로토콜 버전">
              <NativeSelect value={conn.protocolVersion} onChange={(e) => setConn({ ...conn, protocolVersion: e.target.value })}>
                {["2025-06-18", "2025-03-26", "2024-11-05"].map((v) => <option key={v}>{v}</option>)}
              </NativeSelect>
            </Lbl>
            <Lbl label="타임아웃 (ms)">
              <Input type="number" value={conn.timeoutMs} onChange={(e) => setConn({ ...conn, timeoutMs: Number(e.target.value) })} />
            </Lbl>
            <Lbl label="엔드포인트 URL" className="sm:col-span-2">
              <Input className="font-mono text-xs" placeholder="https://mes.internal.example/mcp" value={conn.endpoint} onChange={(e) => setConn({ ...conn, endpoint: e.target.value })} />
            </Lbl>
            <Lbl label="인증 방식">
              <NativeSelect value={conn.auth} onChange={(e) => setConn({ ...conn, auth: e.target.value })}>
                {["OAuth2 Client Credentials", "OAuth2 (사용자 위임)", "API Key", "mTLS", "없음 (사내망 전용)"].map((v) => <option key={v}>{v}</option>)}
              </NativeSelect>
            </Lbl>
            <Lbl label="서버 (시스템 서버 정보)">
              <NativeSelect value={conn.host} onChange={(e) => setConn({ ...conn, host: e.target.value })}>
                <option value="">선택</option>
                {mcpHosts.map((h) => <option key={h.hostname} value={h.hostname}>{h.hostname} · {h.ip} ({SERVER_ENV[h.env]}, {h.role})</option>)}
              </NativeSelect>
            </Lbl>
          </div>
        </Section>

        {/* 5. Tool 정의 */}
        <Section
          no={5}
          title="Tool 정의"
          desc="MCP 서버가 제공하는 Tool을 불러오고, 카탈로그에 공개할 Tool을 고릅니다. 공개한 Tool만 사용자가 신청할 수 있습니다."
          right={tools.length > 0 ? <Badge variant="info">공개 {exposedCount} / 전체 {tools.length}</Badge> : undefined}
        >
          <div className="space-y-4">
            <Tabs<ToolSource>
              value={source}
              onChange={(v) => { setSource(v); setMsg(null); }}
              items={[
                { value: "test", label: "연결 테스트로 불러오기" },
                { value: "json", label: "tools/list JSON" },
                { value: "manual", label: "직접 입력" },
              ]}
            />

            {source === "test" && (
              <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-[#f5f6f8] p-4">
                <Plug className="size-5 text-muted-foreground" />
                <span className="min-w-0 flex-1 text-sm text-muted-foreground">
                  입력한 엔드포인트에 <code className="font-mono text-[12px]">initialize</code> → <code className="font-mono text-[12px]">tools/list</code>를 호출해 Tool 목록을 가져옵니다.
                </span>
                <Button type="button" size="sm" onClick={runTest} disabled={testing}>
                  {testing ? <Loader2 className="animate-spin" /> : <Plug />} {testing ? "연결 중…" : "연결 테스트"}
                </Button>
              </div>
            )}
            {source === "json" && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setJsonText(SAMPLE_TOOLS_LIST)}><FileJson /> 예시 불러오기</Button>
                  <span className="text-xs text-muted-foreground">readOnlyHint가 없으면 이름(get_, list_, search_ …)으로 조회/변경을 판정합니다.</span>
                </div>
                <textarea rows={6} className={cn(textareaCls, "font-mono text-xs")} placeholder='{"result": {"tools": [ ... ]}}' value={jsonText} onChange={(e) => setJsonText(e.target.value)} />
                <div className="flex justify-end">
                  <Button type="button" size="sm" onClick={applyJson} disabled={!jsonText}>가져오기</Button>
                </div>
              </div>
            )}
            {msg && <p className={cn("text-sm", msg.ok ? "text-[#1e8e3e]" : "text-[#d70015]")}>{msg.text}</p>}

            <div className="space-y-1.5">
              <div className="grid grid-cols-[1.3fr_2fr_90px_80px_auto] gap-2 px-1 text-xs text-muted-foreground">
                <span>Tool 이름</span><span>설명</span><span>구분</span><span>공개</span><span className="w-9" />
              </div>
              {tools.map((t, i) => (
                <div key={i} className={cn("grid grid-cols-[1.3fr_2fr_90px_80px_auto] items-center gap-2", !t.exposed && "opacity-55")}>
                  <Input className="h-9 font-mono text-xs" value={t.name} onChange={(e) => upd(i, { name: e.target.value })} />
                  <Input className="h-9 text-xs" value={t.description} onChange={(e) => upd(i, { description: e.target.value })} />
                  <NativeSelect className="h-9 text-xs" value={t.kind} onChange={(e) => upd(i, { kind: e.target.value as Tool["kind"] })}>
                    <option>조회</option>
                    <option>변경</option>
                  </NativeSelect>
                  <button
                    type="button"
                    onClick={() => upd(i, { exposed: !t.exposed })}
                    className={cn("flex h-9 items-center justify-center gap-1 rounded-xl text-xs font-bold ring-1", t.exposed ? "bg-accent text-primary ring-primary/40" : "text-muted-foreground ring-black/[0.08]")}
                  >
                    {t.exposed ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
                    {t.exposed ? "공개" : "숨김"}
                  </button>
                  <Button type="button" variant="ghost" size="icon" onClick={() => setTools(tools.filter((_, j) => j !== i))} aria-label="Tool 삭제">
                    <Trash2 />
                  </Button>
                </div>
              ))}
              {tools.length === 0 && <p className="py-3 text-center text-sm text-muted-foreground">Tool이 없습니다. 연결 테스트나 JSON으로 불러오세요.</p>}
              <Button type="button" variant="outline" size="sm" onClick={() => setTools([...tools, { name: "", description: "", kind: "조회", exposed: true, params: 0 }])}>
                <Plus /> Tool 추가
              </Button>
              {tools.some((t) => t.kind === "변경" && t.exposed) && (
                <p className="rounded-xl bg-[#fff3e0] px-3 py-2 text-[12.5px] text-[#8a5300]">
                  변경 Tool이 공개됩니다. 승인 시 데이터 변경 영향과 가드레일(2차 M4) 적용 대상인지 확인됩니다.
                </p>
              )}
            </div>
          </div>
        </Section>
      </fieldset>
      <ErrorNote error={saveMut.error} />
      {!canRequest && (
        <p className="text-right text-xs text-muted-foreground">승인 요청에는 MCP 서버 이름, 업무명, 엔드포인트, 공개 Tool 1개 이상이 필요합니다.</p>
      )}
    </div>
  );
}
