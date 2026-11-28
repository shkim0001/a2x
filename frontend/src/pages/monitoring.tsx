import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import type { Role } from "@/lib/sample-data";
import type { CallRow, StatRow } from "@/lib/api";
import { useCallDetail, useCallStats, useCalls } from "@/lib/queries";
import { useAgentBridge } from "@/lib/agent-bridge";
import { ErrorNote, Loading } from "@/components/feedback";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/tabs";
import { SearchInput } from "@/components/search-input";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/modal";
import { CallFlow } from "@/components/call-flow";
import { Pager } from "@/components/pager";
import { cn } from "@/lib/utils";

// 모니터링 대메뉴의 하위 화면 3개: API 사용내역 / MCP 사용내역 / 호출 통계 (백엔드 /monitoring/*, 조회 범위는 서버가 판정)
export function ApiUsagePage({ role }: { role: Role }) {
  return <UsageView kind="API" role={role} />;
}
export function McpUsagePage({ role }: { role: Role }) {
  return <UsageView kind="MCP" role={role} />;
}
export function CallStatsPage() {
  return <StatsView />;
}

function scopeLabel(role: Role) {
  return role === "admin" ? "전체 시스템" : role === "시스템 담당자" ? "내가 담당하는 시스템(클라이언트 또는 프로바이더) + 내 호출" : "내 Tool 호출";
}

const pad = (n: number, w = 2) => String(n).padStart(w, "0");
function fmtTime(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// ================= 조회 기간 =================
// 빠른 선택(오늘 · 24시간 · 7일 · 30일)은 끝을 '지금'으로 두고 1분마다 새로고침, '직접 지정'은 시작 · 종료 날짜와 시간.
type Preset = "today" | "1d" | "7d" | "30d" | "custom";
type Period = { preset: Preset; start: string; end: string };
const PRESETS: { value: Preset; label: string }[] = [
  { value: "today", label: "오늘" },
  { value: "1d", label: "24시간" },
  { value: "7d", label: "7일" },
  { value: "30d", label: "30일" },
  { value: "custom", label: "직접 지정" },
];
const localInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const localDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function periodParams(p: Period): { days?: number; start?: string; end?: string } {
  if (p.preset === "1d") return { days: 1 };
  if (p.preset === "7d") return { days: 7 };
  if (p.preset === "30d") return { days: 30 };
  if (p.preset === "today") return { start: `${localDate(new Date())}T00:00` };
  return { start: p.start || undefined, end: p.end || undefined };
}

function periodLabel(p: Period) {
  if (p.preset !== "custom") return { today: "오늘", "1d": "최근 24시간", "7d": "최근 7일", "30d": "최근 30일" }[p.preset];
  return `${p.start.replace("T", " ") || "처음"} ~ ${p.end.replace("T", " ") || "지금"}`;
}

function PeriodPicker({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  const pick = (preset: Preset) => {
    if (preset !== "custom") return onChange({ ...value, preset });
    // 직접 지정으로 바꾸면 지금 보던 기간을 시작값으로 채운다
    const now = new Date();
    const back = { today: 0, "1d": 1, "7d": 7, "30d": 30, custom: 7 }[value.preset];
    const start = value.preset === "today" ? new Date(now.getFullYear(), now.getMonth(), now.getDate()) : new Date(now.getTime() - back * 86_400_000);
    onChange({ preset, start: value.start || localInput(start), end: value.end || localInput(now) });
  };
  const bad = value.preset === "custom" && value.start && value.end && value.end <= value.start;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tabs<Preset> value={value.preset} onChange={pick} items={PRESETS} />
      {value.preset === "custom" && (
        <div className="flex items-center gap-1.5 text-sm">
          <Input type="datetime-local" aria-label="조회 시작" className={cn("h-9 w-[230px]", bad && "ring-2 ring-red-400")} value={value.start} max={value.end || undefined} onChange={(e) => onChange({ ...value, start: e.target.value })} />
          <span className="text-muted-foreground">~</span>
          <Input type="datetime-local" aria-label="조회 종료" className={cn("h-9 w-[230px]", bad && "ring-2 ring-red-400")} value={value.end} min={value.start || undefined} onChange={(e) => onChange({ ...value, end: e.target.value })} />
          {bad && <span className="text-xs text-red-600">종료가 시작보다 뒤여야 합니다</span>}
        </div>
      )}
    </div>
  );
}

// ================= 호출 통계 =================
const ERR_ALERT = 5; // 이 오류율(%)을 넘는 날 · 달을 빨간 점으로 표시
type Unit = "daily" | "monthly";
type Kind = "all" | "api" | "mcp";

function StatsView() {
  const [unit, setUnit] = useState<Unit>("daily");
  const [kind, setKind] = useState<Kind>("all");
  // 기간: 비우면 일별 최근 30일 · 월별 최근 12개월. 월별은 "YYYY-MM"을 그 달 1일로 보낸다
  const [range, setRange] = useState<{ daily: [string, string]; monthly: [string, string] }>({ daily: ["", ""], monthly: ["", ""] });
  const [from, to] = range[unit];
  const asDate = (v: string) => (v ? (unit === "monthly" ? `${v}-01` : v) : undefined);
  const badRange = !!from && !!to && to < from;
  const stats = useCallStats(unit, badRange ? undefined : asDate(from), badRange ? undefined : asDate(to));
  const setEdge = (i: 0 | 1, v: string) => setRange((r) => ({ ...r, [unit]: (i === 0 ? [v, r[unit][1]] : [r[unit][0], v]) as [string, string] }));
  const custom = !!from || !!to;
  const spanLabel = custom
    ? `${from || "처음"} ~ ${to || (unit === "daily" ? "오늘" : "이번 달")}`
    : unit === "daily" ? "최근 30일" : "최근 12개월";
  const rows = stats.data ?? [];
  const val = (r: StatRow) => (kind === "api" ? r.api : kind === "mcp" ? r.mcp : r.api + r.mcp);

  const total = rows.reduce((s, r) => s + val(r), 0);
  const errors = rows.reduce((s, r) => s + r.errors, 0);
  const all = rows.reduce((s, r) => s + r.api + r.mcp, 0);
  const avgMs = all ? Math.round(rows.reduce((s, r) => s + r.avg_ms * (r.api + r.mcp), 0) / all) : 0;
  const peak = rows.length ? rows.reduce((m, r) => (val(r) > val(m) ? r : m), rows[0]) : undefined;
  const max = Math.max(1, ...rows.map((r) => r.api + r.mcp));
  const rate = (r: StatRow) => (r.api + r.mcp ? (r.errors / (r.api + r.mcp)) * 100 : 0);

  const tiles = [
    { label: `총 호출 (${custom ? `${rows.length}${unit === "daily" ? "일" : "개월"}` : unit === "daily" ? "30일" : "12개월"})`, value: total.toLocaleString() },
    { label: "오류율", value: `${all ? ((errors / all) * 100).toFixed(2) : "0.00"}%` },
    { label: "평균 응답시간", value: `${avgMs} ms` },
    { label: `최대 호출 ${unit === "daily" ? "일" : "월"}`, value: peak && val(peak) ? `${peak.label} · ${val(peak).toLocaleString()}` : "-" },
  ];
  if (stats.isLoading) return <Loading />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <Tabs<Unit> value={unit} onChange={setUnit} items={[{ value: "daily", label: "일별" }, { value: "monthly", label: "월별" }]} />
        <Tabs<Kind> value={kind} onChange={setKind} items={[{ value: "all", label: "전체" }, { value: "api", label: "API" }, { value: "mcp", label: "MCP" }]} />
        <div className="flex items-center gap-1.5 text-sm">
          <Input type={unit === "daily" ? "date" : "month"} aria-label="통계 시작" className={cn("h-9 w-[160px]", badRange && "ring-2 ring-red-400")} value={from} onChange={(e) => setEdge(0, e.target.value)} />
          <span className="text-muted-foreground">~</span>
          <Input type={unit === "daily" ? "date" : "month"} aria-label="통계 종료" className={cn("h-9 w-[160px]", badRange && "ring-2 ring-red-400")} value={to} onChange={(e) => setEdge(1, e.target.value)} />
          {custom && <Button variant="ghost" size="sm" onClick={() => setRange((r) => ({ ...r, [unit]: ["", ""] }))}>기본 기간</Button>}
          {badRange && <span className="text-xs text-red-600">종료가 시작보다 뒤여야 합니다</span>}
        </div>
      </div>
      <ErrorNote error={stats.error} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map((t) => (
          <Card key={t.label}>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{t.label}</p>
              <p className="mt-2 font-display font-bold tracking-[-0.025em] text-[28px] leading-none">{t.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>{unit === "daily" ? "일별" : "월별"}({spanLabel}) 호출 추이</CardTitle>
            <CardDescription>막대 위에 마우스를 올리면 수치가 보입니다.</CardDescription>
          </div>
          <div className="flex gap-3 text-xs">
            {(kind === "all" || kind === "api") && <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-primary/80" />API</span>}
            {(kind === "all" || kind === "mcp") && <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-violet-400" />MCP</span>}
          </div>
        </CardHeader>
        <CardContent>
          <div className={cn("flex h-56 items-end", rows.length > 62 ? "gap-px" : "gap-1")}>
            {rows.map((r) => {
              const err = rate(r);
              return (
                <div
                  key={r.key}
                  className="group flex h-full flex-1 flex-col items-center justify-end gap-1"
                  title={`${r.label}\nAPI ${r.api.toLocaleString()} · MCP ${r.mcp.toLocaleString()}\n오류 ${r.errors.toLocaleString()} (${err.toFixed(2)}%) · 평균 ${r.avg_ms}ms`}
                >
                  {err > ERR_ALERT && <span className="size-1.5 rounded-full bg-red-500" />}
                  <div className="flex w-full flex-col justify-end overflow-hidden rounded-t-sm group-hover:opacity-80" style={{ height: `${(val(r) / max) * 190}px` }}>
                    {kind !== "api" && <div className="bg-violet-400" style={{ flexGrow: r.mcp }} />}
                    {kind !== "mcp" && <div className="bg-primary/80" style={{ flexGrow: r.api }} />}
                  </div>
                </div>
              );
            })}
          </div>
          <div className={cn("mt-1 flex", rows.length > 62 ? "gap-px" : "gap-1")}>
            {rows.map((r, i) => {
              // 기간이 길어도 눈금 글자가 겹치지 않게 약 8~12개만 보인다
              const step = Math.max(1, Math.ceil(rows.length / (unit === "monthly" ? 12 : 8)));
              return (
                <span key={r.key} className="flex min-w-0 flex-1 justify-center overflow-visible whitespace-nowrap text-[10px] text-muted-foreground">
                  {i % step === 0 || i === rows.length - 1 ? r.label : ""}
                </span>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-muted-foreground"><span className="mr-1 inline-block size-1.5 rounded-full bg-red-500" />오류율 {ERR_ALERT}% 초과</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{unit === "daily" ? "일별" : "월별"} 통계표</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>{unit === "daily" ? "일자" : "월"}</TH>
                <TH className="text-right">API 호출</TH>
                <TH className="text-right">MCP 호출</TH>
                <TH className="text-right">합계</TH>
                <TH className="text-right">오류</TH>
                <TH className="text-right">오류율</TH>
                <TH className="text-right">평균 응답(ms)</TH>
              </TR>
            </THead>
            <TBody>
              {[...rows].reverse().map((r) => {
                const err = rate(r);
                return (
                  <TR key={r.key}>
                    <TD>{r.label}</TD>
                    <TD className="text-right">{r.api.toLocaleString()}</TD>
                    <TD className="text-right">{r.mcp.toLocaleString()}</TD>
                    <TD className="text-right font-medium">{(r.api + r.mcp).toLocaleString()}</TD>
                    <TD className="text-right">{r.errors.toLocaleString()}</TD>
                    <TD className={cn("text-right", err > ERR_ALERT && "font-medium text-red-600")}>{err.toFixed(2)}%</TD>
                    <TD className="text-right">{r.avg_ms}</TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ================= 사용내역 (API · MCP) =================
type StatusFilter = "전체" | "성공" | "실패";

function UsageView({ kind, role }: { kind: "API" | "MCP"; role: Role }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("전체");
  const [selected, setSelected] = useState<string | null>(null);
  const query = useDebounced(q);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20); // 페이지당 기본 20건
  const [period, setPeriod] = useState<Period>({ preset: "7d", start: "", end: "" });
  const badPeriod = period.preset === "custom" && !!period.start && !!period.end && period.end <= period.start;
  const range = periodParams(period);
  const statusParam = status === "성공" ? "success" : status === "실패" ? "failed" : undefined;
  // 필터 · 검색어가 바뀌면 첫 페이지로
  useEffect(() => {
    setPage(1);
  }, [kind, statusParam, query, size, period]);
  const calls = useCalls({ kind, status: statusParam, q: query || undefined, ...range, page, size, ...(badPeriod ? { days: 7, start: undefined, end: undefined } : {}) });
  const rows: CallRow[] = calls.data?.items ?? [];
  const total = calls.data?.total ?? 0;
  // 실패 건수는 기간 전체 기준(현재 페이지가 아니라)
  const failed = useCalls({ kind, status: "failed", q: query || undefined, ...range, page: 1, size: 1, ...(badPeriod ? { days: 7, start: undefined, end: undefined } : {}) });
  // 연 트랜잭션은 Agent 문맥으로 넘긴다(오류 조치 Agent가 이 건을 진단)
  const { setFocus } = useAgentBridge();
  useEffect(() => {
    setFocus(selected ? { transaction_id: selected } : {});
  }, [selected, setFocus]);

  const failCount = status === "성공" ? 0 : (failed.data?.total ?? 0);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle>{kind} 사용내역</CardTitle>
          <CardDescription>
            {periodLabel(period)} {total.toLocaleString()}건 · 실패 {failCount.toLocaleString()}건 · 조회 범위: {scopeLabel(role)}. Status를 누르면 트랜잭션 상세를 볼 수 있습니다.
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Tabs<StatusFilter>
            value={status}
            onChange={setStatus}
            items={(["전체", "성공", "실패"] as StatusFilter[]).map((v) => ({ value: v, label: v }))}
          />
          <SearchInput value={q} onChange={setQ} placeholder="이름, 시스템, URI, 코드" className="w-64" />
        </div>
        <div className="w-full">
          <PeriodPicker value={period} onChange={setPeriod} />
          <ErrorNote error={calls.error} className="mt-2" />
        </div>
      </CardHeader>
      <CardContent>
        <Table className="whitespace-nowrap text-xs">
          <THead>
            <TR>
              <TH>Status</TH>
              <TH>Return Code</TH>
              <TH>{kind === "API" ? "API Name" : "MCP 서버 · Tool"}</TH>
              <TH>클라이언트 시스템</TH>
              <TH>프로바이더 시스템</TH>
              <TH>Start time</TH>
              <TH>End time</TH>
              <TH className="text-right">Duration</TH>
              <TH>Client IP</TH>
              {kind === "MCP" && <TH>사용자 ID</TH>}
              <TH>Protocol</TH>
              <TH>Method</TH>
              <TH>Uri</TH>
              <TH>Error Message</TH>
            </TR>
          </THead>
          <TBody>
            {rows.map((r) => (
              <TR key={r.tx_id}>
                <TD>
                  <button onClick={() => setSelected(r.tx_id)} className="cursor-pointer" aria-label={`${r.tx_id} 상세 보기`}>
                    <Badge variant={r.success ? "success" : "danger"} className="hover:ring-2 hover:ring-ring/40">
                      {r.success ? "성공" : "실패"}
                    </Badge>
                  </button>
                </TD>
                <TD className={cn("font-mono", Number(r.return_code) >= 400 && "text-red-600")}>{r.return_code}</TD>
                <TD className="font-medium">{r.name}</TD>
                <TD>{r.client_system.name}</TD>
                <TD>{r.provider_system.name}</TD>
                <TD className="font-mono text-muted-foreground">{fmtTime(r.started_at)}</TD>
                <TD className="font-mono text-muted-foreground">{fmtTime(r.ended_at)}</TD>
                <TD className={cn("text-right font-mono", r.duration_ms >= 3000 && "text-amber-700")}>{r.duration_ms.toLocaleString()} ms</TD>
                <TD className="font-mono">{r.client_ip}</TD>
                {kind === "MCP" && <TD className="font-mono" title={r.user ?? undefined}>{r.user_login ?? "-"}</TD>}
                <TD>{r.protocol}</TD>
                <TD className="font-mono">{r.method}</TD>
                <TD className="max-w-72 truncate font-mono" title={r.uri}>{r.uri}</TD>
                <TD className="max-w-64 truncate text-red-600" title={r.error_message}>{r.error_message}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
        {calls.isLoading && <Loading />}
        <ErrorNote error={calls.error} />
        {!calls.isLoading && rows.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">해당하는 내역이 없습니다.</p>}
        {total > 0 && (
          <div className="mt-3">
            <Pager page={page} size={size} total={total} onPage={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} onSize={setSize} loading={calls.isFetching} />
          </div>
        )}
      </CardContent>
      {selected && <TxDetail txId={selected} onClose={() => setSelected(null)} />}
    </Card>
  );
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-56 overflow-auto rounded-2xl bg-[#1d1d1f] p-3 text-xs leading-relaxed text-zinc-100">
      {value === null || value === undefined ? "(없음)" : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function TxDetail({ txId, onClose }: { txId: string; onClose: () => void }) {
  const detail = useCallDetail(txId);
  const { ask } = useAgentBridge();
  const row = detail.data;

  return (
    <Modal
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          트랜잭션 상세
          {row && <Badge variant={row.success ? "success" : "danger"}>{row.success ? "성공" : "실패"}</Badge>}
          <span className="font-mono text-xs font-normal text-muted-foreground">{txId}</span>
        </span>
      }
    >
      {!row ? (
        detail.error ? <ErrorNote error={detail.error} /> : <Loading />
      ) : (
        <div className="space-y-5 text-sm">
          <CallFlow row={row} />

          <div className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
            {(
              [
                ["트랜잭션 ID", row.tx_id],
                ["Return Code", row.return_code],
                [row.kind === "API" ? "API Name" : "MCP 서버 · Tool", row.name],
                ["클라이언트 시스템", `${row.client_system.name} (${row.client_ip})`],
                ["프로바이더 시스템", row.provider_system.name],
                ...(row.user ? [["사용자", row.user_login ? `${row.user} (${row.user_login})` : row.user]] : []),
                ["시스템 구독", row.subscription_id ? `#${row.subscription_id}` : "-"],
                ["Start time", fmtTime(row.started_at)],
                ["End time", fmtTime(row.ended_at)],
                ["Duration", `${row.duration_ms.toLocaleString()} ms`],
                ["Protocol · Method", `${row.protocol} · ${row.method}`],
              ] as [string, string][]
            ).map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-muted-foreground">{k}</p>
                <p className="mt-0.5 break-all">{v}</p>
              </div>
            ))}
            <div className="sm:col-span-3">
              <p className="text-xs text-muted-foreground">Uri</p>
              <p className="mt-0.5 break-all font-mono text-xs">{row.uri}</p>
            </div>
          </div>

          {!row.success && (
            <div className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="font-medium text-red-800">{row.error_message}</p>
              {row.classification && (
                <p className="text-red-900/80">
                  <span className="font-medium">규칙 분류:</span> {row.classification.category} — {row.classification.action}
                </p>
              )}
              <Button size="sm" variant="outline" onClick={() => ask(`${row.tx_id} 오류 원인과 조치 알려줘`)}>
                <Bot /> 오류 조치 Agent에 분석 요청
              </Button>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="mb-2 font-medium">요청 헤더</p>
              <Json value={row.request_headers} />
            </div>
            <div>
              <p className="mb-2 font-medium">요청 본문</p>
              <Json value={row.request_body} />
            </div>
          </div>
          <div>
            <p className="mb-2 font-medium">응답 본문</p>
            <Json value={row.response_body} />
            <p className="mt-1 text-xs text-muted-foreground">인증 정보와 개인정보는 마스킹되어 저장됩니다.</p>
          </div>
        </div>
      )}
    </Modal>
  );
}
