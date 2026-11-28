// 모니터링 › 인스턴스 모니터링: A2X 구성요소(포탈 · Gateway · MCP 서버 · 외부 MCP · Agent · 운영 데이터)가 정상인지 한 화면에서 본다.
// 판정은 서버(src/monitoring/health.py)가 하고, 화면은 상태를 색으로 보여 준다. 비정상은 맨 위 경보와 빨간 테두리로 바로 드러난다.
import { useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleSlash, RefreshCw, XCircle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { get, type InstanceComponent, type InstanceGroup, type InstanceStatus, type Instances } from "@/lib/api";
import { useInstances } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorNote, Loading } from "@/components/feedback";
import { cn } from "@/lib/utils";

const LABEL: Record<InstanceStatus, string> = { ok: "정상", warn: "주의", down: "비정상", off: "점검 제외" };
const DOT: Record<InstanceStatus, string> = { ok: "bg-[#34c759]", warn: "bg-amber-400", down: "bg-red-500", off: "bg-[#c7c7cc]" };
const PILL: Record<InstanceStatus, string> = {
  ok: "bg-[#e6f6ea] text-[#1e6b34]",
  warn: "bg-amber-50 text-amber-800",
  down: "bg-red-50 text-red-700",
  off: "bg-[#f2f2f4] text-[#6e6e73]",
};
const ICON: Record<InstanceStatus, typeof CheckCircle2> = { ok: CheckCircle2, warn: AlertTriangle, down: XCircle, off: CircleSlash };

function Dot({ s }: { s: InstanceStatus }) {
  return (
    <span className="relative flex size-2.5 shrink-0">
      {s === "down" && <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-400 opacity-75" />}
      <span className={cn("relative inline-flex size-2.5 rounded-full", DOT[s])} />
    </span>
  );
}

function Pill({ s }: { s: InstanceStatus }) {
  const Icon = ICON[s];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-bold", PILL[s])}>
      <Icon className="size-3.5" /> {LABEL[s]}
    </span>
  );
}

const fmt = (iso: string) => new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function InstancesPage() {
  const [auto, setAuto] = useState(true);
  const q = useInstances(auto);
  const qc = useQueryClient();
  const [checking, setChecking] = useState(false);
  // '지금 점검': 서버 캐시 없이 다시 점검
  const recheck = async () => {
    setChecking(true);
    try {
      qc.setQueryData(["instances"], await get<Instances>("/monitoring/instances?refresh=true"));
    } finally {
      setChecking(false);
    }
  };
  const d = q.data;
  if (q.isLoading) return <Loading />;
  if (!d) return <ErrorNote error={q.error} />;

  const all = d.groups.flatMap((g) => g.components.map((c) => ({ ...c, group: g.label, groupKey: g.key })));
  const bad = all.filter((c) => c.status === "down" || c.status === "warn").sort((a, b) => (a.status === "down" ? -1 : 0) - (b.status === "down" ? -1 : 0));
  const byKey = Object.fromEntries(d.groups.map((g) => [g.key, g]));
  const go = (key: string) => document.getElementById(`comp-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" });

  return (
    <div className="space-y-4">
      {/* 전체 상태 경보 */}
      <Card className={cn(d.status === "down" && "ring-2 ring-red-400", d.status === "warn" && "ring-2 ring-amber-300")}>
        <CardContent className="flex flex-wrap items-center gap-4 p-5">
          <div className={cn("grid size-12 place-items-center rounded-2xl", d.status === "down" ? "bg-red-50 text-red-600" : d.status === "warn" ? "bg-amber-50 text-amber-600" : "bg-[#e6f6ea] text-[#1e6b34]")}>
            {(() => {
              const Icon = ICON[d.status];
              return <Icon className="size-6" />;
            })()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-display text-[22px] font-bold tracking-[-0.02em]">
              {d.status === "down" ? `비정상 ${d.counts.down}개 — 바로 확인이 필요합니다` : d.status === "warn" ? `주의 ${d.counts.warn}개` : "모든 구성요소 정상"}
            </p>
            <p className="text-[13px] text-muted-foreground">
              마지막 점검 {fmt(d.checked_at)} · {auto ? "15초마다 자동 점검" : "자동 점검 꺼짐"} · 호스트 {d.host.name} ({d.host.os}, Python {d.host.python})
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(["ok", "warn", "down", "off"] as InstanceStatus[]).map((s) => (
              <span key={s} className={cn("flex items-center gap-1.5 rounded-full px-3 py-1 text-[13px] font-bold", PILL[s])}>
                <Dot s={s} /> {LABEL[s]} {d.counts[s]}
              </span>
            ))}
            <label className="ml-1 flex items-center gap-1.5 text-[13px]">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> 자동
            </label>
            <Button size="sm" variant="outline" onClick={recheck} disabled={checking}>
              <RefreshCw className={cn(checking && "animate-spin")} /> 지금 점검
            </Button>
          </div>
          {bad.length > 0 && (
            <div className="flex w-full flex-wrap gap-1.5 border-t border-black/[0.05] pt-3">
              {bad.map((c) => (
                <button key={c.key} onClick={() => go(c.key)} className={cn("flex items-center gap-1.5 rounded-full px-3 py-1 text-[12.5px] font-bold hover:opacity-80", PILL[c.status])}>
                  <Dot s={c.status} /> {c.group} › {c.name}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 호출 경로: 사용자 → 포탈 → 권한 Gateway → MCP · API Gateway → MCP 서버 · 외부 MCP */}
      <Card>
        <CardHeader>
          <CardTitle>구성요소 흐름</CardTitle>
          <CardDescription>Agent · 사용자 호출이 지나가는 순서. 칸을 누르면 그 묶음으로 이동합니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-stretch gap-2">
            {(["portal", "perm-gw", "data-gw", "mcp-servers", "external"] as const).map((k, i, arr) => {
              const g = byKey[k];
              if (!g) return null;
              return (
                <div key={k} className="flex items-center gap-2">
                  <FlowNode g={g} />
                  {i < arr.length - 1 && <ArrowRight className="size-4 shrink-0 text-muted-foreground" />}
                </div>
              );
            })}
            <span className="mx-2 w-px self-stretch bg-black/[0.06]" />
            {(["agent", "ops"] as const).map((k) => byKey[k] && <FlowNode key={k} g={byKey[k]} />)}
          </div>
        </CardContent>
      </Card>

      {/* 묶음별 상세 */}
      <div className="grid gap-4 xl:grid-cols-2">
        {d.groups.map((g) => (
          <Card key={g.key} id={`group-${g.key}`} className={cn(g.status === "down" && "ring-2 ring-red-300", g.key === "mcp-servers" && "xl:col-span-2")}>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div>
                <CardTitle>{g.label}</CardTitle>
                <CardDescription>{g.desc}</CardDescription>
              </div>
              <Pill s={g.status} />
            </CardHeader>
            <CardContent className={cn("grid gap-2", g.key === "mcp-servers" && "md:grid-cols-2")}>
              {g.components.map((c) => (
                <ComponentRow key={c.key} c={c} />
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      <ErrorNote error={q.error} />
    </div>
  );
}

function FlowNode({ g }: { g: InstanceGroup }) {
  const n = { down: g.components.filter((c) => c.status === "down").length, warn: g.components.filter((c) => c.status === "warn").length };
  return (
    <button
      onClick={() => document.getElementById(`group-${g.key}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
      className={cn(
        "flex min-w-[150px] flex-col items-start gap-1 rounded-2xl px-3.5 py-2.5 text-left ring-1 transition hover:-translate-y-0.5",
        g.status === "down" ? "bg-red-50 ring-red-300" : g.status === "warn" ? "bg-amber-50 ring-amber-200" : g.status === "off" ? "bg-[#f5f6f8] ring-black/[0.06]" : "bg-[#f3fbf5] ring-[#c4ebcf]",
      )}
    >
      <span className="flex items-center gap-1.5 text-[13px] font-bold">
        <Dot s={g.status} /> {g.label}
      </span>
      <span className="text-[11.5px] text-muted-foreground">
        {g.components.length}개{n.down ? ` · 비정상 ${n.down}` : ""}{n.warn ? ` · 주의 ${n.warn}` : ""}
      </span>
    </button>
  );
}

function ComponentRow({ c }: { c: InstanceComponent }) {
  return (
    <div
      id={`comp-${c.key}`}
      className={cn(
        "flex items-start gap-3 rounded-2xl p-3 ring-1",
        c.status === "down" ? "bg-red-50/70 ring-red-200" : c.status === "warn" ? "bg-amber-50/60 ring-amber-200" : "bg-white ring-black/[0.06]",
      )}
    >
      <span className="mt-1.5">
        <Dot s={c.status} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-bold">{c.name}</span>
          {c.kind && <Badge variant="secondary">{c.kind}</Badge>}
          <span className={cn("text-[11.5px] font-bold", c.status === "down" ? "text-red-600" : c.status === "warn" ? "text-amber-700" : "text-muted-foreground")}>{LABEL[c.status]}</span>
        </div>
        <p className="mt-0.5 text-[12.5px] text-[#3a3a3c]">{c.detail}</p>
        {c.endpoint && <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground" title={c.endpoint}>{c.endpoint}</p>}
      </div>
      {c.latency_ms !== null && c.latency_ms !== undefined && (
        <span className={cn("shrink-0 font-mono text-[12px]", c.latency_ms > 1000 ? "text-amber-700" : "text-muted-foreground")}>{c.latency_ms}ms</span>
      )}
    </div>
  );
}
