// 구독 · 권한 › 카탈로그 › 사용 신청 화면: 담은 API · MCP 여러 개를 한 번에 신청한다.
// - Tool 사용 신청(개인): MCP 서버마다 사용할 Agent 연계와 Tool을 고른다.
// - 시스템 구독 신청(담당자): 내 시스템 하나로 담은 항목을 한꺼번에 구독 신청한다.
// 승인 규칙 · 중복 판정은 서버가 항목마다 한다. 화면은 항목별 결과(성공 · 실패 사유)를 보여 준다.
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bot, Check, CircleAlert, Server, X } from "lucide-react";
import type { Role } from "@/lib/sample-data";
import { errText, useAction, useAssets, useConnections, useSystems } from "@/lib/queries";
import { post, type AssetSummary, type ConnectionOut, type FormSuggestion, type SystemOut, type ToolRequestOut } from "@/lib/api";
import { SYSTEM_KIND, TOOL_KIND } from "@/lib/labels";
import { useAgentBridge } from "@/lib/agent-bridge";
import { AgentFilledNote } from "@/components/agent-filled";
import { AssetIconTile } from "@/components/asset-icon";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Tabs } from "@/components/tabs";
import { Empty, Loading } from "@/components/feedback";
import { cn } from "@/lib/utils";

type Mode = "tool" | "system";
type Result = { assetId: number; name: string; ok: boolean; text: string };
type Pick = { subId: number; tools: Set<string> };

export function RequestScreen({
  ids,
  role,
  prefill,
  onBack,
  onRemove,
  onSent,
}: {
  ids: number[];
  role: Role;
  prefill: FormSuggestion | null;
  onBack: () => void;
  onRemove: (id: number) => void;
  onSent: (okIds: number[]) => void;
}) {
  const all = useAssets().data;
  const assets = useMemo(() => ids.map((id) => all?.find((a) => a.id === id)).filter((a): a is AssetSummary => !!a), [ids, all]);
  const systems = useSystems().data ?? [];
  const connections = useConnections().data ?? [];
  const isManager = role !== "일반 사용자";
  const mcps = assets.filter((a) => a.type === "MCP");
  const hasConnection = mcps.some((a) => connections.some((c) => c.asset.id === a.id));
  const [mode, setMode] = useState<Mode | null>(prefill ? "system" : null);
  const current: Mode = mode ?? (hasConnection || !isManager ? "tool" : "system");
  const [results, setResults] = useState<Result[] | null>(null);

  // 화면 문맥: 하나만 담았으면 그 자산을 Agent에게 넘긴다
  const { setFocus } = useAgentBridge();
  useEffect(() => {
    setFocus(ids.length === 1 ? { asset_id: ids[0] } : {});
  }, [ids, setFocus]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, []);

  if (!all) return <Loading />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={onBack}>
          <ArrowLeft /> 카탈로그로
        </Button>
        <h3 className="font-display text-[24px] font-bold tracking-[-0.025em]">사용 신청 · {assets.length}건</h3>
        <span className="text-[13px] text-muted-foreground">승인은 항목마다 프로바이더 시스템 담당자가 합니다.</span>
      </div>

      {/* 담은 항목 */}
      <Card>
        <CardContent className="flex flex-wrap gap-2 p-4">
          {assets.map((a) => (
            <span key={a.id} className="flex items-center gap-2 rounded-2xl bg-[#f5f6f8] py-1.5 pr-2 pl-1.5 text-sm">
              <AssetIconTile asset={a} size={26} />
              <span className="font-bold">{a.name}</span>
              <Badge variant={a.type === "MCP" ? "violet" : "info"}>{a.type}</Badge>
              <span className="text-[12px] text-muted-foreground">{a.system.name}</span>
              {!results && assets.length > 1 && (
                <button onClick={() => onRemove(a.id)} aria-label={`${a.name} 빼기`} className="rounded-full p-0.5 text-muted-foreground hover:bg-black/5">
                  <X className="size-3.5" />
                </button>
              )}
            </span>
          ))}
          {assets.length === 0 && <Empty>담은 항목이 없습니다. 카탈로그에서 담아 주세요.</Empty>}
        </CardContent>
      </Card>

      {results ? (
        <ResultView results={results} onBack={onBack} />
      ) : (
        assets.length > 0 && (
          <>
            <Tabs<Mode>
              value={current}
              onChange={setMode}
              items={[
                { value: "tool", label: "Tool 사용 신청 (개인)" },
                { value: "system", label: "시스템 구독 신청 (담당자)" },
              ]}
            />
            {current === "tool" ? (
              <ToolRequests assets={assets} connections={connections} isManager={isManager} onGoSystem={() => setMode("system")} onDone={(r) => { setResults(r); onSent(r.filter((x) => x.ok).map((x) => x.assetId)); }} />
            ) : isManager ? (
              <SystemRequests assets={assets} systems={systems} prefill={prefill} onDone={(r) => { setResults(r); onSent(r.filter((x) => x.ok).map((x) => x.assetId)); }} />
            ) : (
              <p className="rounded-2xl bg-[#fff3e0] p-4 text-sm text-[#8a5300]">시스템 구독은 시스템 담당자가 신청합니다. 소속 시스템 담당자에게 요청하세요.</p>
            )}
          </>
        )
      )}
    </div>
  );
}

// 항목마다 따로 보내고, 실패해도 나머지는 계속 보낸다
async function sendEach<T>(items: T[], send: (x: T) => Promise<string>, label: (x: T) => { assetId: number; name: string }): Promise<Result[]> {
  const settled = await Promise.allSettled(items.map(send));
  return settled.map((s, i) => ({ ...label(items[i]), ok: s.status === "fulfilled", text: s.status === "fulfilled" ? s.value : errText(s.reason) }));
}

function ToolRequests({
  assets,
  connections,
  isManager,
  onGoSystem,
  onDone,
}: {
  assets: AssetSummary[];
  connections: ConnectionOut[];
  isManager: boolean;
  onGoSystem: () => void;
  onDone: (r: Result[]) => void;
}) {
  const mcps = assets.filter((a) => a.type === "MCP");
  const apis = assets.filter((a) => a.type === "API");
  const [picks, setPicks] = useState<Record<number, Pick>>({});
  const [purpose, setPurpose] = useState("");
  const connOf = (assetId: number) => connections.filter((c) => c.asset.id === assetId);
  const pickOf = (assetId: number): Pick => picks[assetId] ?? { subId: connOf(assetId)[0]?.subscription_id ?? 0, tools: new Set() };
  const setPick = (assetId: number, p: Pick) => setPicks((cur) => ({ ...cur, [assetId]: p }));
  const toggle = (assetId: number, name: string) => {
    const p = pickOf(assetId);
    const tools = new Set(p.tools);
    if (tools.has(name)) tools.delete(name);
    else tools.add(name);
    setPick(assetId, { ...p, tools });
  };
  const chosen = mcps.filter((a) => pickOf(a.id).tools.size > 0);
  const total = chosen.reduce((n, a) => n + pickOf(a.id).tools.size, 0);

  const send = useAction(() =>
    sendEach(
      chosen,
      async (a) => {
        const p = pickOf(a.id);
        const r = await post<{ created: ToolRequestOut[]; skipped: string[] }>("/tool-requests", { subscription_id: p.subId, tools: [...p.tools], purpose });
        return `Tool ${r.created.length}개 신청${r.skipped.length ? ` · 이미 신청 · 사용 중이라 건너뜀: ${r.skipped.join(", ")}` : ""}`;
      },
      (a) => ({ assetId: a.id, name: a.name }),
    ),
  );

  return (
    <div className="space-y-4">
      {mcps.map((a) => {
        const conns = connOf(a.id);
        const p = pickOf(a.id);
        const conn = conns.find((c) => c.subscription_id === p.subId) ?? conns[0];
        return (
          <Card key={a.id}>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <AssetIconTile asset={a} size={30} />
                <div>
                  <CardTitle>{a.name}</CardTitle>
                  <CardDescription className="flex items-center gap-1.5"><Server className="size-3.5" />{a.system.name} · {a.system.dept}</CardDescription>
                </div>
              </div>
              {conns.length > 0 && (
                <label className="flex items-center gap-2 text-sm">
                  <span className="font-bold">사용할 Agent</span>
                  <NativeSelect className="w-64" value={conn.subscription_id} onChange={(e) => setPick(a.id, { subId: Number(e.target.value), tools: new Set() })}>
                    {conns.map((c) => <option key={c.subscription_id} value={c.subscription_id}>{c.client_system.name} → {a.name}</option>)}
                  </NativeSelect>
                </label>
              )}
            </CardHeader>
            <CardContent>
              {conns.length === 0 ? (
                <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-[#f5f6f8] p-4 text-sm">
                  <Bot className="size-5 text-muted-foreground" />
                  <span>이 MCP 서버를 구독한 Agent 시스템이 없어 Tool을 신청할 수 없습니다. Agent 시스템이 먼저 시스템 구독을 받아야 합니다.</span>
                  {isManager && <Button variant="outline" size="sm" className="ml-auto" onClick={onGoSystem}>시스템 구독 신청으로</Button>}
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {conn.tools.map((t) => {
                    const on = p.tools.has(t.name);
                    const status = t.my_status;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        disabled={!!status}
                        onClick={() => toggle(a.id, t.name)}
                        className={cn(
                          "flex items-start gap-3 rounded-2xl p-3 text-left text-sm ring-1 transition-all",
                          status ? "cursor-not-allowed bg-[#f5f6f8] opacity-60 ring-transparent" : on ? "bg-accent ring-2 ring-primary" : "bg-white ring-black/[0.08] hover:ring-primary/40",
                        )}
                      >
                        <span className={cn("mt-0.5 grid size-5 shrink-0 place-items-center rounded-md ring-1", on ? "bg-primary text-white ring-primary" : "ring-black/20")}>
                          {on && <Check className="size-3.5" />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-1.5">
                            <span className="font-mono text-[13px] font-bold">{t.name}</span>
                            {t.kind === "WRITE" && <Badge variant="warning">{TOOL_KIND[t.kind]}</Badge>}
                          </span>
                          <span className="block text-[12.5px] text-muted-foreground">{t.description || "설명 없음"}</span>
                          {status && <span className="mt-1 block text-[11.5px] font-bold text-primary">{status === "APPROVED" ? "사용 중" : "승인 대기"}</span>}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
      {apis.length > 0 && (
        <p className="rounded-2xl bg-[#fff3e0] p-4 text-sm text-[#8a5300]">
          API({apis.map((a) => a.name).join(", ")})는 Tool 신청 대상이 아닙니다. 시스템 구독 신청 탭에서 시스템 단위로 신청합니다.
        </p>
      )}
      {mcps.length > 0 && (
        <SubmitBar
          purpose={purpose}
          setPurpose={setPurpose}
          placeholder="예: 상담 중 고객 재고 확인"
          summary={`MCP ${chosen.length}개 · Tool ${total}개 선택`}
          label="Tool 한 번에 신청"
          disabled={total === 0 || !purpose.trim() || send.isPending}
          pending={send.isPending}
          onSubmit={() => send.mutate(undefined, { onSuccess: onDone })}
        />
      )}
    </div>
  );
}

function SystemRequests({ assets, systems, prefill, onDone }: { assets: AssetSummary[]; systems: SystemOut[]; prefill: FormSuggestion | null; onDone: (r: Result[]) => void }) {
  const mine = useSystems({ mine: true }).data ?? [];
  const [from, setFrom] = useState<number | null>(prefill?.values.client_system_id ?? null);
  const [purpose, setPurpose] = useState<string>(prefill?.values.purpose ?? "");
  const [note, setNote] = useState(prefill);
  const clientId = from ?? mine[0]?.id;
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  // 내 시스템이 제공하는 항목은 구독 대상이 아니다
  const own = (a: AssetSummary) => a.system.id === clientId;
  const targets = assets.filter((a) => !own(a) && !excluded.has(a.id));
  const managersOf = (systemId: number) => systems.find((s) => s.id === systemId)?.managers.map((m) => m.name).join(", ") ?? "-";

  const send = useAction(() =>
    sendEach(
      targets,
      async (a) => {
        await post("/subscriptions", { client_system_id: clientId, asset_id: a.id, purpose });
        return a.type === "MCP" ? "시스템 구독 신청 · 승인 후 사용자가 Tool을 신청합니다" : "시스템 구독 신청";
      },
      (a) => ({ assetId: a.id, name: a.name }),
    ),
  );

  if (mine.length === 0) return <p className="rounded-2xl bg-[#f5f6f8] p-4 text-sm text-muted-foreground">신청할 수 있는 내 시스템이 없습니다.</p>;

  return (
    <div className="space-y-4">
      {note && <AgentFilledNote s={note} onClose={() => setNote(null)} />}
      <Card>
        <CardHeader>
          <CardTitle>구독할 내 시스템</CardTitle>
          <CardDescription>선택한 시스템(클라이언트)으로 아래 항목을 한꺼번에 구독 신청합니다. API는 시스템 구독만으로 쓰고, MCP는 구독 승인 후 사용자가 Tool을 신청합니다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <NativeSelect className="max-w-md" value={clientId} onChange={(e) => setFrom(Number(e.target.value))}>
            {mine.map((s) => <option key={s.id} value={s.id}>{s.name} ({SYSTEM_KIND[s.kind]})</option>)}
          </NativeSelect>
          <div className="divide-y divide-black/[0.05] rounded-2xl ring-1 ring-black/[0.06]">
            {assets.map((a) => {
              const skip = own(a);
              const on = !skip && !excluded.has(a.id);
              return (
                <label key={a.id} className={cn("flex items-center gap-3 px-4 py-3 text-sm", skip ? "opacity-60" : "cursor-pointer hover:bg-[#fafafa]")}>
                  <input
                    type="checkbox"
                    disabled={skip}
                    checked={on}
                    onChange={() => setExcluded((cur) => { const n = new Set(cur); if (n.has(a.id)) n.delete(a.id); else n.add(a.id); return n; })}
                  />
                  <AssetIconTile asset={a} size={26} />
                  <span className="font-bold">{a.name}</span>
                  <Badge variant={a.type === "MCP" ? "violet" : "info"}>{a.type}</Badge>
                  <span className="ml-auto text-[12.5px] text-muted-foreground">
                    {skip ? "내 시스템이 제공하는 항목이라 제외" : `${a.system.name} · 승인 ${managersOf(a.system.id)}`}
                  </span>
                </label>
              );
            })}
          </div>
        </CardContent>
      </Card>
      <SubmitBar
        purpose={purpose}
        setPurpose={setPurpose}
        placeholder="예: 고객 문의 시 주문 · 재고 확인"
        summary={`${targets.length}건 구독 신청`}
        label="한 번에 구독 신청"
        disabled={!clientId || targets.length === 0 || !purpose.trim() || send.isPending}
        pending={send.isPending}
        onSubmit={() => send.mutate(undefined, { onSuccess: onDone })}
      />
    </div>
  );
}

function SubmitBar(p: { purpose: string; setPurpose: (v: string) => void; placeholder: string; summary: string; label: string; disabled: boolean; pending: boolean; onSubmit: () => void }) {
  return (
    <Card className="sticky bottom-4 z-10 shadow-[0_12px_40px_rgb(0_0_0/0.12)]">
      <CardContent className="flex flex-wrap items-center gap-3 p-4">
        <label className="flex min-w-[280px] flex-1 items-center gap-2 text-sm">
          <span className="shrink-0 font-bold">사용 목적</span>
          <Input value={p.purpose} onChange={(e) => p.setPurpose(e.target.value)} placeholder={p.placeholder} />
        </label>
        <span className="text-sm text-muted-foreground">{p.summary}</span>
        <Button disabled={p.disabled} onClick={p.onSubmit}>{p.pending ? "보내는 중…" : p.label}</Button>
      </CardContent>
    </Card>
  );
}

function ResultView({ results, onBack }: { results: Result[]; onBack: () => void }) {
  const ok = results.filter((r) => r.ok).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>신청 결과 · 성공 {ok}건{results.length - ok > 0 && ` · 실패 ${results.length - ok}건`}</CardTitle>
        <CardDescription>프로바이더 시스템 담당자가 승인하면 '구독 · 권한' 메뉴(내 권한 · 구독 · 승인)에서 확인할 수 있습니다. 실패한 항목은 카탈로그에 담긴 채로 남습니다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {results.map((r) => (
          <div key={r.assetId} className={cn("flex items-start gap-3 rounded-2xl p-3.5 text-sm", r.ok ? "bg-[#e6f6ea] text-[#1e6b34]" : "bg-[#fdecec] text-[#a1261b]")}>
            {r.ok ? <Check className="mt-0.5 size-4 shrink-0" /> : <CircleAlert className="mt-0.5 size-4 shrink-0" />}
            <span className="font-bold">{r.name}</span>
            <span>{r.text}</span>
          </div>
        ))}
        <div className="flex justify-end pt-2">
          <Button onClick={onBack}>카탈로그로</Button>
        </div>
      </CardContent>
    </Card>
  );
}
