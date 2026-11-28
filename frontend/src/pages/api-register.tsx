import { useState, type ReactNode } from "react";
import { Check, Download, FileJson, FileSpreadsheet, Plus, Sparkles, Trash2, Upload } from "lucide-react";
import { PROCESSES, type ApiSpec, type AssetIcon, type HttpMethod, type LayoutField, type Operation, type Role } from "@/lib/sample-data";
import { get, parseExcelLayout, post, put, type AssetDetail, type AssetStatus } from "@/lib/api";
import { ASSET_STATUS, DATA_LEVEL, LIFECYCLE_STEPS, SERVER_ENV } from "@/lib/labels";
import { useAction, useSystems } from "@/lib/queries";
import { AssetIconPicker, normalizeIcon, toIconIn } from "@/components/asset-icon";
import { ErrorNote } from "@/components/feedback";
import { AgentFilledNote, agentRing } from "@/components/agent-filled";
import { useAgentBridge, useEditRequest, useSuggestion } from "@/lib/agent-bridge";
import type { FormSuggestion } from "@/lib/api";
import { CSV_TEMPLATE, SAMPLE_SWAGGER, inferFromJson, parseCsv, parseSwagger } from "@/lib/layout-import";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/tabs";
import { cn } from "@/lib/utils";

type LayoutSource = "excel" | "swagger" | "json" | "manual";
type Target = "request" | "response";

const METHODS: HttpMethod[] = ["GET", "POST", "PUT", "DELETE"];
export const textareaCls =
  "w-full rounded-md border border-input bg-card px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function Section({ no, title, desc, children, right, hl }: { no: number; title: string; desc?: string; children: ReactNode; right?: ReactNode; hl?: boolean }) {
  return (
    <Card className={cn(hl && agentRing)}>
      <CardHeader className="flex-row items-start justify-between">
        <div className="flex gap-3">
          <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">{no}</span>
          <div>
            <CardTitle>{title}</CardTitle>
            {desc && <CardDescription className="mt-1">{desc}</CardDescription>}
          </div>
        </div>
        {right}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function Lbl({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block space-y-1.5 text-sm", className)}>
      <span className="font-medium">{label}</span>
      {children}
    </label>
  );
}

export function ReadOnly({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm">{value || "-"}</p>
    </div>
  );
}

export function ApiRegisterForm({ role }: { role: Role }) {
  // API는 내가 담당하는 업무 시스템에만 등록한다(admin은 전체)
  const mySystems = (useSystems({ mine: role !== "admin", kind: "BUSINESS" }).data ?? []);
  const [pickedSystem, setSystemId] = useState<number | null>(null);
  const systemId = pickedSystem ?? mySystems[0]?.id ?? 0;
  const sys = mySystems.find((s) => s.id === systemId);

  const [savedId, setSavedId] = useState<number | undefined>();
  const [status, setStatus] = useState<AssetStatus | undefined>();

  const [basic, setBasic] = useState({ name: "", version: "1.0.0", description: "" });
  const [icon, setIcon] = useState<AssetIcon | undefined>();
  const [business, setBusiness] = useState<ApiSpec["business"]>({
    category: sys?.process ?? PROCESSES[0], name: "", program: "", detail: "", impact: "중",
  });
  const [direction, setDirection] = useState<ApiSpec["direction"]>("송신");
  const [tech, setTech] = useState({ baseUrl: "", auth: "OAuth2 Client Credentials", contentType: "application/json", timeoutMs: 5000 });
  const [resources, setResources] = useState<Operation[]>([{ method: "GET", path: "", summary: "" }]);
  const [layouts, setLayouts] = useState<Record<Target, LayoutField[]>>({ request: [], response: [] });

  const [source, setSource] = useState<LayoutSource>("swagger");
  const [target, setTarget] = useState<Target>("response");
  const [importText, setImportText] = useState("");
  const [importMsg, setImportMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // 승인 이후(스테이지 · 운영 · 중지)에 고쳐 저장하면 다시 승인 대기로 돌아간다(재승인)
  const approved = status === "STAGE" || status === "LIVE" || status === "SUSPENDED";
  const pending = status === "PENDING";

  // ---- 레이아웃 가져오기 ----
  const applySwagger = (text: string) => {
    try {
      const r = parseSwagger(text);
      setLayouts({ request: r.requestLayout, response: r.responseLayout });
      if (r.resources.length) setResources(r.resources);
      setBasic((b) => ({ ...b, name: b.name || r.title, version: r.version || b.version }));
      if (r.baseUrl) setTech((t) => ({ ...t, baseUrl: r.baseUrl }));
      setImportMsg({ ok: true, text: `리소스 ${r.resources.length}개, 요청 필드 ${r.requestLayout.length}개, 응답 필드 ${r.responseLayout.length}개를 가져왔습니다. (레이아웃은 첫 오퍼레이션 기준)` });
    } catch (e) {
      setImportMsg({ ok: false, text: (e as Error).message });
    }
  };
  const applyJson = () => {
    try {
      const fields = inferFromJson(importText);
      setLayouts((l) => ({ ...l, [target]: fields }));
      setImportMsg({ ok: true, text: `${target === "request" ? "요청" : "응답"} 필드 ${fields.length}개를 추출했습니다.` });
    } catch {
      setImportMsg({ ok: false, text: "JSON 형식이 올바르지 않습니다." });
    }
  };
  const onFile = async (file: File) => {
    const text = await file.text();
    if (source === "swagger") return applySwagger(text);
    if (/\.xlsx$/i.test(file.name)) {
      try {
        const fields = await parseExcelLayout(file);
        setLayouts((l) => ({ ...l, [target]: fields }));
        setImportMsg({ ok: true, text: `${target === "request" ? "요청" : "응답"} 필드 ${fields.length}개를 엑셀에서 가져왔습니다.` });
      } catch (e) {
        setImportMsg({ ok: false, text: (e as Error).message });
      }
      return;
    }
    const fields = parseCsv(text);
    setLayouts((l) => ({ ...l, [target]: fields }));
    setImportMsg({ ok: true, text: `${target === "request" ? "요청" : "응답"} 필드 ${fields.length}개를 가져왔습니다.` });
  };
  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob(["﻿" + CSV_TEMPLATE], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "api_layout_template.csv" });
    a.click();
    URL.revokeObjectURL(url);
  };

  const updField = (i: number, patch: Partial<LayoutField>) =>
    setLayouts((l) => ({ ...l, [target]: l[target].map((f, j) => (j === i ? { ...f, ...patch } : f)) }));

  // ---- Agent 자동 채움: 패널의 '양식에 채우기' 또는 아래 버튼(Agent에게 요청) ----
  const bridge = useAgentBridge();
  const [agentFilled, setAgentFilled] = useState<FormSuggestion | null>(null);
  // Agent 제안과 저장된 API 불러오기가 같은 값 형식(AssetDetail)을 쓴다
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fill = (v: Record<string, any>) => {
    const IMPACT_LABEL = { HIGH: "상", MEDIUM: "중", LOW: "하" } as const;
    if (v.system_id) setSystemId(v.system_id);
    if (v.name) setBasic({ name: v.name, version: v.version ?? "1.0.0", description: v.description ?? "" });
    if (v.business) {
      const b = v.business;
      setBusiness({ category: b.category || business.category, name: b.name ?? "", program: b.program ?? "", detail: b.detail ?? "", impact: IMPACT_LABEL[b.impact as keyof typeof IMPACT_LABEL] ?? "중" });
    }
    if (v.direction) setDirection(v.direction === "RECEIVE" ? "수신" : "송신");
    if (v.base_url !== undefined) setTech({ baseUrl: v.base_url ?? "", auth: v.auth_type || tech.auth, contentType: v.content_type ?? "application/json", timeoutMs: v.timeout_ms ?? 5000 });
    if (v.operations?.length) setResources(v.operations);
    if (v.request_layout || v.response_layout) setLayouts({ request: v.request_layout ?? [], response: v.response_layout ?? [] });
  };
  useSuggestion("api", (s) => {
    fill(s.values);
    setAgentFilled(s);
  });
  // 카탈로그 '수정': 저장된 API를 불러와 같은 양식에서 고친다
  const [loadError, setLoadError] = useState<unknown>(null);
  useEditRequest("API", (id) => {
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
  const askAgent = () => bridge.ask(`${sys?.code ?? ""} ${basic.name} API 등록 채워줘`.replace(/\s+/g, " ").trim());

  // ---- 저장 / 승인 요청 ----
  const IMPACT_CODE = { 상: "HIGH", 중: "MEDIUM", 하: "LOW" } as const;
  const payload = (submit: boolean) => ({
    system_id: systemId,
    name: basic.name,
    version: basic.version,
    description: basic.description,
    icon: toIconIn(icon),
    business: { ...business, impact: IMPACT_CODE[business.impact] },
    direction: direction === "송신" ? "SEND" : "RECEIVE",
    base_url: tech.baseUrl,
    auth_type: tech.auth,
    content_type: tech.contentType,
    timeout_ms: tech.timeoutMs,
    operations: resources.filter((r) => r.path),
    request_layout: layouts.request.filter((f) => f.name),
    response_layout: layouts.response.filter((f) => f.name),
    submit,
  });
  // 처음엔 등록(POST), 저장한 뒤에는 수정(PUT). submit=true면 승인 요청까지
  const saveMut = useAction((submit: boolean) =>
    savedId ? put<AssetDetail>(`/assets/${savedId}/api`, payload(submit)) : post<AssetDetail>("/assets/api", payload(submit)),
  );
  const save = (next: "DRAFT" | "PENDING") =>
    saveMut.mutate(next === "PENDING", {
      onSuccess: (a) => {
        setSavedId(a.id);
        setStatus(a.status);
        setAgentFilled(null);
      },
    });
  const canSave = !!systemId && !!basic.name && !saveMut.isPending;
  const canRequest = canSave && !!business.name && resources.some((r) => r.path) && !!tech.baseUrl;

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
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm",
                    i < currentStep && "border-emerald-200 bg-emerald-50 text-emerald-800",
                    i === currentStep && "border-primary bg-accent font-medium text-accent-foreground",
                    i > currentStep && "text-muted-foreground",
                  )}
                >
                  {i < currentStep ? <Check className="size-3.5" /> : <span className="text-xs">{i + 1}</span>}
                  {s.label}
                </div>
                {i < LIFECYCLE_STEPS.length - 1 && <span className="h-px w-6 bg-border" />}
              </div>
            ))}
            {status === "REJECTED" && <Badge variant="danger">반려됨 — 수정 후 다시 요청</Badge>}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={askAgent} title="외부 마스터(API 마스터)에서 읽어 채울 값을 Agent가 제안합니다">
              <Sparkles /> Agent로 채우기
            </Button>
            {approved ? (
              <Button onClick={() => confirm(`승인된 API를 고치면 다시 승인 대기로 돌아가고, 재승인 · 운영 전환 전까지 호출할 수 없습니다. 저장할까요?`) && save("PENDING")} disabled={!canRequest}>
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
        <Section hl={!!agentFilled} no={1} title="시스템 정보" desc="시스템 마스터에서 가져옵니다. 내가 담당하는 시스템만 선택할 수 있습니다.">
          <div className="grid gap-4 sm:grid-cols-3">
            <Lbl label="시스템">
              <NativeSelect value={systemId} disabled={!!savedId} onChange={(e) => setSystemId(Number(e.target.value))}>
                {mySystems.map((s) => <option key={s.id} value={s.id}>{s.code !== s.name ? `${s.name} (${s.code})` : s.name}</option>)}
              </NativeSelect>
            </Lbl>
            <ReadOnly label="업무 프로세스" value={sys?.process} />
            <ReadOnly label="소속 부서" value={sys?.dept} />
            <ReadOnly label="담당자" value={sys?.managers.map((m) => m.name).join(", ")} />
            <ReadOnly label="데이터 등급" value={sys && DATA_LEVEL[sys.data_level]} />
            <ReadOnly label="서버" value={sys?.servers.map((s) => `${s.hostname}(${SERVER_ENV[s.env]})`).join(", ")} />
          </div>
        </Section>

        {/* 2. 기본정보 */}
        <Section hl={!!agentFilled} no={2} title="기본정보">
          <div className="grid gap-4 sm:grid-cols-3">
            <Lbl label="API 이름"><Input value={basic.name} onChange={(e) => setBasic({ ...basic, name: e.target.value })} /></Lbl>
            <Lbl label="버전"><Input value={basic.version} onChange={(e) => setBasic({ ...basic, version: e.target.value })} /></Lbl>
            <ReadOnly label="등록 진행상태" value={status ? ASSET_STATUS[status] : "작성 중 (미저장)"} />
            <Lbl label="설명" className="sm:col-span-3"><Input value={basic.description} onChange={(e) => setBasic({ ...basic, description: e.target.value })} /></Lbl>
            <div className="space-y-1.5 text-sm sm:col-span-3">
              <span className="font-medium">카탈로그 대표 이미지</span>
              <AssetIconPicker value={icon} onChange={setIcon} fallback={{ type: "API", systemId }} />
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
                    className={cn(
                      "flex-1 rounded-md border py-1.5",
                      business.impact === v ? (v === "상" ? "border-red-300 bg-red-50 text-red-800" : "border-primary bg-accent") : "hover:bg-muted",
                    )}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* 4. API 타입 정의 */}
        <Section hl={!!agentFilled} no={4} title="API 타입 정의">
          <div className="space-y-1.5 text-sm">
            <span className="font-medium">데이터 방향 ({sys?.name ?? "시스템"} 기준)</span>
            <div className="flex gap-2">
              {([
                ["송신", "이 시스템이 데이터를 제공한다 (다른 시스템이 호출해 가져감)"],
                ["수신", "이 시스템이 데이터를 받는다 (다른 시스템이 호출해 전달함)"],
              ] as const).map(([v, d]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setDirection(v)}
                  className={cn("flex-1 rounded-2xl bg-[#f5f6f8] p-3.5 transition-colors hover:bg-[#eef1f6] text-left", direction === v ? "border-primary bg-accent" : "hover:bg-muted")}
                >
                  <p className="font-medium">{v}</p>
                  <p className="text-xs text-muted-foreground">{d}</p>
                </button>
              ))}
            </div>
          </div>
        </Section>

        {/* 5. 레이아웃 */}
        <Section hl={!!agentFilled} no={5} title="레이아웃" desc="요청 · 응답 필드 정의. 엑셀 업로드, Swagger import, Sample JSON으로 가져오거나 직접 입력합니다.">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs<LayoutSource>
                value={source}
                onChange={(v) => { setSource(v); setImportMsg(null); setImportText(""); }}
                items={[
                  { value: "excel", label: "엑셀 업로드" },
                  { value: "swagger", label: "Swagger import" },
                  { value: "json", label: "Sample JSON" },
                  { value: "manual", label: "직접 입력" },
                ]}
              />
              {source !== "swagger" && (
                <Tabs<Target>
                  value={target}
                  onChange={setTarget}
                  items={[
                    { value: "request", label: `요청 ${layouts.request.length}` },
                    { value: "response", label: `응답 ${layouts.response.length}` },
                  ]}
                />
              )}
            </div>

            {source === "excel" && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-4 text-sm">
                <FileSpreadsheet className="size-5 text-muted-foreground" />
                <span className="text-muted-foreground">필드명, 타입, 필수(Y/N), 설명 열이 있는 엑셀(.xlsx) 또는 CSV를 올립니다.</span>
                <Button type="button" variant="ghost" size="sm" onClick={downloadTemplate}><Download /> 템플릿</Button>
                <label className="ml-auto">
                  <input type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
                  <span className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"><Upload className="size-4" /> 파일 선택</span>
                </label>
              </div>
            )}

            {source === "swagger" && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <label>
                    <input type="file" accept=".json,.yaml,.yml" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
                    <span className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border bg-card px-3 text-xs font-medium shadow-sm hover:bg-accent"><Upload className="size-4" /> Swagger 파일 (.json / .yaml)</span>
                  </label>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setImportText(SAMPLE_SWAGGER)}><FileJson /> 예시 불러오기</Button>
                  <span className="text-xs text-muted-foreground">리소스(Define resource)와 Base URL도 함께 채웁니다.</span>
                </div>
                <textarea rows={6} className={cn(textareaCls, "font-mono text-xs")} placeholder="OpenAPI 3.x / Swagger 2.0 문서(JSON 또는 YAML)를 붙여 넣으세요" value={importText} onChange={(e) => setImportText(e.target.value)} />
                <div className="flex justify-end">
                  <Button type="button" size="sm" onClick={() => applySwagger(importText)} disabled={!importText}>가져오기</Button>
                </div>
              </div>
            )}

            {source === "json" && (
              <div className="space-y-2">
                <textarea
                  rows={6}
                  className={cn(textareaCls, "font-mono text-xs")}
                  placeholder={'{\n  "orderId": "A-1001",\n  "items": [{ "sku": "P-01", "qty": 2 }]\n}'}
                  value={importText}
                  onChange={(e) => setImportText(e.target.value)}
                />
                <div className="flex justify-end">
                  <Button type="button" size="sm" onClick={applyJson} disabled={!importText}>
                    {target === "request" ? "요청" : "응답"} 필드 추출
                  </Button>
                </div>
              </div>
            )}

            {importMsg && <p className={cn("text-sm", importMsg.ok ? "text-emerald-700" : "text-red-600")}>{importMsg.text}</p>}

            {source === "swagger" && (
              <Tabs<Target>
                value={target}
                onChange={setTarget}
                items={[
                  { value: "request", label: `요청 ${layouts.request.length}` },
                  { value: "response", label: `응답 ${layouts.response.length}` },
                ]}
              />
            )}

            <div className="space-y-1.5">
              <div className="grid grid-cols-[1.6fr_0.9fr_0.5fr_2fr_auto] gap-2 px-1 text-xs text-muted-foreground">
                <span>필드명</span><span>타입</span><span>필수</span><span>설명</span><span className="w-9" />
              </div>
              {layouts[target].map((f, i) => (
                <div key={i} className="grid grid-cols-[1.6fr_0.9fr_0.5fr_2fr_auto] items-center gap-2">
                  <Input className="h-8 font-mono text-xs" value={f.name} onChange={(e) => updField(i, { name: e.target.value })} />
                  <NativeSelect className="h-8 text-xs" value={f.type} onChange={(e) => updField(i, { type: e.target.value })}>
                    {["string", "integer", "number", "boolean", "object", "array", "null"].map((t) => <option key={t}>{t}</option>)}
                  </NativeSelect>
                  <input type="checkbox" className="justify-self-center" checked={f.required} onChange={(e) => updField(i, { required: e.target.checked })} />
                  <Input className="h-8 text-xs" value={f.description} onChange={(e) => updField(i, { description: e.target.value })} />
                  <Button type="button" variant="ghost" size="icon" onClick={() => setLayouts((l) => ({ ...l, [target]: l[target].filter((_, j) => j !== i) }))} aria-label="필드 삭제">
                    <Trash2 />
                  </Button>
                </div>
              ))}
              {layouts[target].length === 0 && <p className="py-3 text-center text-sm text-muted-foreground">필드가 없습니다.</p>}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLayouts((l) => ({ ...l, [target]: [...l[target], { name: "", type: "string", required: false, description: "" }] }))}
              >
                <Plus /> 필드 추가
              </Button>
            </div>
          </div>
        </Section>

        {/* 6. Define resource */}
        <Section hl={!!agentFilled} no={6} title="Define resource" desc="HTTP 메소드, URL 패턴 등 기술 정보. 등록 후 'API → MCP 변환'에서 리소스별로 MCP Tool을 만들 수 있습니다.">
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-4">
              <Lbl label="Base URL" className="sm:col-span-2">
                <Input className="font-mono text-xs" placeholder="https://host/api/v1" value={tech.baseUrl} onChange={(e) => setTech({ ...tech, baseUrl: e.target.value })} />
              </Lbl>
              <Lbl label="인증 방식">
                <NativeSelect value={tech.auth} onChange={(e) => setTech({ ...tech, auth: e.target.value })}>
                  {["없음", "API Key", "Basic", "OAuth2 Client Credentials", "JWT"].map((v) => <option key={v}>{v}</option>)}
                </NativeSelect>
              </Lbl>
              <Lbl label="타임아웃 (ms)">
                <Input type="number" value={tech.timeoutMs} onChange={(e) => setTech({ ...tech, timeoutMs: Number(e.target.value) })} />
              </Lbl>
              <Lbl label="Content-Type">
                <NativeSelect value={tech.contentType} onChange={(e) => setTech({ ...tech, contentType: e.target.value })}>
                  {["application/json", "application/xml", "text/plain", "multipart/form-data"].map((v) => <option key={v}>{v}</option>)}
                </NativeSelect>
              </Lbl>
            </div>

            <div className="space-y-1.5">
              <div className="grid grid-cols-[110px_1.5fr_1.5fr_auto] gap-2 px-1 text-xs text-muted-foreground">
                <span>메소드</span><span>URL 패턴</span><span>설명</span><span className="w-9" />
              </div>
              {resources.map((r, i) => (
                <div key={i} className="grid grid-cols-[110px_1.5fr_1.5fr_auto] gap-2">
                  <NativeSelect value={r.method} onChange={(e) => setResources(resources.map((x, j) => (j === i ? { ...x, method: e.target.value as HttpMethod } : x)))}>
                    {METHODS.map((m) => <option key={m}>{m}</option>)}
                  </NativeSelect>
                  <Input className="font-mono text-xs" placeholder="/orders/{orderId}" value={r.path} onChange={(e) => setResources(resources.map((x, j) => (j === i ? { ...x, path: e.target.value } : x)))} />
                  <Input value={r.summary} onChange={(e) => setResources(resources.map((x, j) => (j === i ? { ...x, summary: e.target.value } : x)))} />
                  <Button type="button" variant="ghost" size="icon" onClick={() => setResources(resources.filter((_, j) => j !== i))} aria-label="리소스 삭제">
                    <Trash2 />
                  </Button>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" onClick={() => setResources([...resources, { method: "GET", path: "", summary: "" }])}>
                <Plus /> 리소스 추가
              </Button>
            </div>
          </div>
        </Section>
      </fieldset>
      <ErrorNote error={saveMut.error} />
      {!canRequest && (
        <p className="text-right text-xs text-muted-foreground">승인 요청에는 API 이름, 업무명, Base URL, 리소스 1개 이상이 필요합니다.</p>
      )}
    </div>
  );
}
