import type { ReactNode } from "react";
import { Bot, Boxes, CheckCircle2, Server, ShieldCheck, XCircle } from "lucide-react";
import type { CallDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

// 트랜잭션 호출 흐름: 클라이언트 시스템 → A2X Gateway → 타겟 시스템(API · MCP), 구간별 응답시간 표시
// 원본 호출 단계: 샘플 로그(대상 API 호출 · MCP 서버 호출)와 A2X 중계 로그(원본 API 호출 · 원본 MCP 호출)
const UPSTREAM = new Set(["대상 API 호출", "MCP 서버 호출", "원본 API 호출", "원본 MCP 호출"]);
const isUpstream = (name: string) => UPSTREAM.has(name);

export function CallFlow({ row }: { row: CallDetail }) {
  const recv = row.stages.find((s) => s.name === "Gateway 수신");
  const checks = row.stages.filter((s) => s !== recv && !isUpstream(s.name) && s.name !== "응답 반환");
  const up = row.stages.find((s) => isUpstream(s.name));
  const resp = row.stages.find((s) => s.name === "응답 반환");

  const gwMs = (recv?.ms ?? 0) + checks.reduce((a, s) => a + s.ms, 0);
  const upMs = up?.ms ?? 0;
  const respMs = resp?.ms ?? 1;
  const blocked = checks.find((s) => !s.ok); // Gateway에서 차단된 검사
  const upFailed = !!up && !up.ok;
  const ok = row.success;
  const [mcpServer, mcpTool] = row.name.split(" · ");

  const segs = [
    { label: "A2X Gateway 처리", ms: gwMs, color: blocked ? "#ff3b30" : "#0071e3" },
    ...(up ? [{ label: row.kind === "API" ? "타겟 API 응답" : "MCP 서버 응답", ms: upMs, color: upFailed ? "#ff3b30" : "#7d5cf5" }] : []),
    { label: "응답 반환", ms: respMs, color: ok ? "#34c759" : "#ff9500" },
  ];
  const total = segs.reduce((a, s) => a + s.ms, 0);

  return (
    <div className="rounded-[20px] bg-[#f5f6f8] p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="font-bold">호출 흐름</p>
        <span className="font-mono text-[13px] text-muted-foreground">
          총 <b className="text-foreground">{row.duration_ms.toLocaleString()} ms</b>
        </span>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(84px,0.75fr)_minmax(0,1.25fr)_minmax(84px,0.75fr)_minmax(0,1fr)] items-center">
        {/* 클라이언트 시스템 */}
        <FlowNode
          tone="#5e5ce6"
          icon={row.kind === "MCP" ? <Bot className="size-4" /> : <Server className="size-4" />}
          title={row.client_system.name}
          lines={[`Client ${row.client_ip}`, ...(row.user ? [`사용자 ${row.user}`] : [])]}
        />

        <FlowArrow req={row.method} reqMs={recv?.ms} res={row.return_code} resMs={respMs} resBad={!ok} color="#0071e3" />

        {/* A2X Gateway: 검사 항목별 통과 여부와 시간 */}
        <div className={cn("rounded-2xl bg-white p-3 ring-2", blocked ? "ring-[#ff3b30]/60" : "ring-primary/40")}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[13px] font-extrabold">
              <span className="grid size-6 place-items-center rounded-lg bg-gradient-to-br from-[#2f6bff] to-[#7d5cf5] text-white">
                <ShieldCheck className="size-3.5" />
              </span>
              A2X Gateway
            </span>
            <span className="font-mono text-[12px] font-bold text-primary">{gwMs} ms</span>
          </div>
          <div className="space-y-1">
            {checks.map((s) => (
              <div
                key={s.name}
                className={cn(
                  "flex items-center justify-between rounded-lg px-2 py-1 text-[11.5px]",
                  s.ok ? "bg-[#ecf9ef] text-[#1e6b34]" : "bg-[#fdecee] font-bold text-[#d70015]",
                )}
              >
                <span className="flex items-center gap-1">
                  {s.ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
                  {s.name}
                </span>
                <span className="font-mono">{s.ms} ms</span>
              </div>
            ))}
          </div>
        </div>

        {up ? (
          <FlowArrow req={row.kind === "API" ? "호출" : "tools/call"} reqMs={upMs} res={upFailed ? "실패" : "응답"} resBad={upFailed} color="#7d5cf5" strong />
        ) : (
          <div className="flex flex-col items-center gap-1.5 px-2 text-[11px] font-bold text-[#d70015]">
            <div className="h-[2px] w-full bg-[repeating-linear-gradient(90deg,#ffb3b8_0_4px,transparent_4px_8px)]" />
            <span>차단 · 호출 안 함</span>
          </div>
        )}

        {/* 타겟 시스템 */}
        <FlowNode
          tone={row.kind === "API" ? "#0066cc" : "#7d5cf5"}
          icon={row.kind === "API" ? <Server className="size-4" /> : <Boxes className="size-4" />}
          title={row.provider_system.name}
          lines={row.kind === "API" ? [row.name, row.uri] : [mcpServer, `Tool ${mcpTool}`]}
          dim={!up}
          badge={
            up ? (
              <span className={cn("rounded-full px-2 py-0.5 font-mono text-[11px] font-bold", upFailed ? "bg-[#fdecee] text-[#d70015]" : "bg-[#f1ecff] text-[#6e4ff6]")}>
                {upMs.toLocaleString()} ms
              </span>
            ) : undefined
          }
        />
      </div>

      {/* 시간 막대: 전체 소요시간을 구간별로 */}
      <div className="mt-5">
        <div className="flex h-3 gap-[2px] overflow-hidden rounded-full bg-white ring-1 ring-black/[0.05]">
          {segs.map((s) => (
            <div key={s.label} title={`${s.label} ${s.ms} ms`} style={{ width: `${Math.max(3, (s.ms / total) * 100)}%`, background: s.color }} />
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
          {segs.map((s) => (
            <span key={s.label} className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: s.color }} />
              {s.label}
              <b className="font-mono">{s.ms.toLocaleString()} ms</b>
              <span className="text-muted-foreground">({Math.round((s.ms / total) * 100)}%)</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function FlowNode({ tone, icon, title, lines, dim, badge }: { tone: string; icon: ReactNode; title: string; lines: string[]; dim?: boolean; badge?: ReactNode }) {
  return (
    <div className={cn("rounded-2xl bg-white p-3 ring-1 ring-black/[0.05]", dim && "opacity-45")}>
      <div className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-xl text-white" style={{ background: tone }}>
          {icon}
        </span>
        <span className="min-w-0 truncate text-[13.5px] font-extrabold tracking-[-0.01em]">{title}</span>
      </div>
      <div className="mt-2 space-y-0.5">
        {lines.map((l, i) => (
          <p key={l} className={cn("truncate text-muted-foreground", i === 0 ? "text-[12px] font-medium text-[#3a3a3c]" : "font-mono text-[11px]")} title={l}>
            {l}
          </p>
        ))}
      </div>
      {(badge || dim) && <div className="mt-2">{badge ?? <span className="text-[11px] font-bold text-muted-foreground">호출 안 됨</span>}</div>}
    </div>
  );
}

// 위: 요청(→), 아래: 응답(←). 요청선 위로 점이 흐른다.
function FlowArrow({ req, reqMs, res, resMs, resBad, color, strong }: { req: string; reqMs?: number; res: string; resMs?: number; resBad?: boolean; color: string; strong?: boolean }) {
  const resColor = resBad ? "#ff3b30" : "#34c759";
  return (
    <div className="flex flex-col gap-2.5 px-2">
      <div className="text-center whitespace-nowrap">
        <span className="text-[11px] font-bold" style={{ color }}>{req}</span>
        {reqMs !== undefined && (
          <span className={cn("ml-1 font-mono text-[11px]", strong ? "font-extrabold text-foreground" : "text-muted-foreground")}>{reqMs.toLocaleString()}ms</span>
        )}
        <div className="relative mt-1 h-[2px] rounded-full" style={{ background: color }}>
          <span className="flow-x absolute top-1/2 size-2 -translate-y-1/2 rounded-full bg-white" style={{ boxShadow: `0 0 0 2px ${color}` }} />
          <span className="absolute top-1/2 -right-0.5 size-0 -translate-y-1/2 border-y-[5px] border-l-[7px] border-y-transparent" style={{ borderLeftColor: color }} />
        </div>
      </div>
      <div className="text-center">
        <div className="relative h-[2px] rounded-full" style={{ background: resColor }}>
          <span className="absolute top-1/2 -left-0.5 size-0 -translate-y-1/2 border-y-[5px] border-r-[7px] border-y-transparent" style={{ borderRightColor: resColor }} />
        </div>
        <span className="mt-1 inline-block text-[11px] font-bold" style={{ color: resBad ? "#d70015" : "#1e8e3e" }}>{res}</span>
        {resMs !== undefined && <span className="ml-1 font-mono text-[11px] text-muted-foreground">{resMs}ms</span>}
      </div>
    </div>
  );
}
