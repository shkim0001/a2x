import { useMemo, useState, type ReactNode } from "react";
import { BookOpen, Bot, Plug, RotateCcw, Route, Server, ShieldCheck, Sparkles, User, X } from "lucide-react";
import type { AgentRoute, TraceStep } from "@/lib/api";
import { cn } from "@/lib/utils";

// Agent 한 번의 실행 흐름을 시퀀스 다이어그램으로 그린다(백엔드 src/shared/trace.py가 남긴 단계).
// 세로선 = 참여 모듈, 화살표 = 호출(누가 → 누구에게 · 무엇을 · 결과 · 걸린 시간). 자기 자신으로 가는 화살표는 코드 판정 단계.

type Part = { name: string; sub: string; color: string; icon: ReactNode };

const AGENT_NAME: Record<string, string> = { consult: "컨설팅", automation: "자동화", devsupport: "개발 지원", error: "오류 조치" };
const ORDER = ["user", "guard", "supervisor", "agent", "portal", "rag", "mcp", "llm"];

const MCP_NAME: Record<string, [string, string]> = { master: ["마스터 MCP", "API · MCP 마스터"], IRP: ["IRP MCP", "시스템 마스터"], DCM: ["DCM MCP", "서버 자산"] };

function part(id: string): Part {
  if (id.startsWith("mcp:")) {
    const [name, sub] = MCP_NAME[id.slice(4)] ?? [`${id.slice(4)} MCP`, "외부 시스템"];
    return { name, sub, color: "#db2777", icon: <Plug className="size-3.5" /> };
  }
  if (id.startsWith("agent:")) {
    return { name: `${AGENT_NAME[id.slice(6)] ?? id.slice(6)} Agent`, sub: "업무 Agent", color: "#7d5cf5", icon: <Bot className="size-3.5" /> };
  }
  const map: Record<string, Part> = {
    user: { name: "사용자", sub: "채팅", color: "#6e6e73", icon: <User className="size-3.5" /> },
    guard: { name: "Guard", sub: "가드레일", color: "#d97706", icon: <ShieldCheck className="size-3.5" /> },
    supervisor: { name: "Supervisor", sub: "규칙 라우팅", color: "#0071e3", icon: <Route className="size-3.5" /> },
    portal: { name: "포탈 Tool", sub: "DB 조회", color: "#0d9488", icon: <Server className="size-3.5" /> },
    rag: { name: "RAG", sub: "ChromaDB", color: "#1e8e3e", icon: <BookOpen className="size-3.5" /> },
    mcp: { name: "마스터 MCP", sub: "외부 마스터", color: "#db2777", icon: <Plug className="size-3.5" /> },
    llm: { name: "LLM", sub: "Claude", color: "#bf5af2", icon: <Sparkles className="size-3.5" /> },
  };
  return map[id] ?? { name: id, sub: "", color: "#6e6e73", icon: null };
}

const W = 520; // 그림 안쪽 너비(px)
const ROW = 62; // 단계 하나의 높이
const STEP_DELAY = 0.22; // 단계마다 나타나는 간격(초)

export function AgentFlow({ steps, route, question, onClose }: { steps: TraceStep[]; route?: AgentRoute; question?: string; onClose: () => void }) {
  const [replay, setReplay] = useState(0);
  // 등장한 참여자만, 정해진 순서로
  const parts = useMemo(() => {
    const ids = [...new Set(steps.flatMap((s) => [s.src, s.dst]))];
    const rank = (x: string) => ORDER.indexOf(x.startsWith("agent:") ? "agent" : x.startsWith("mcp:") ? "mcp" : x);
    const first = [...ids]; // 정렬 전 등장 순서
    return ids.sort((a, b) => rank(a) - rank(b) || first.indexOf(a) - first.indexOf(b)); // 같은 종류(MCP 여럿)는 처음 등장한 순서
  }, [steps]);
  const col = W / Math.max(parts.length, 1);
  const x = (id: string) => parts.indexOf(id) * col + col / 2;

  const count = (dst: string) => steps.filter((s) => (dst === "mcp" ? s.dst.startsWith("mcp:") : s.dst === dst) && s.src !== s.dst).length;
  const totalMs = steps.reduce((sum, s) => sum + (s.ms ?? 0), 0);
  const stats = [
    ["RAG", count("rag")],
    ["MCP", count("mcp")],
    ["포탈 Tool", count("portal")],
    ["LLM", steps.filter((s) => s.dst === "llm" && s.ok).length],
  ] as const;

  return (
    <aside className="page-in fixed top-[100px] right-[420px] bottom-5 z-40 flex w-[560px] flex-col overflow-hidden rounded-[22px] bg-white/95 shadow-[0_24px_70px_rgb(0_0_0/0.14),0_0_0_1px_rgb(0_0_0/0.05)] backdrop-blur-xl">
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-black/[0.06] px-5 py-3.5">
        <div className="min-w-0">
          <p className="font-display text-[17px] font-bold tracking-[-0.02em]">Agent 실행 흐름</p>
          <p className="truncate text-[12px] text-muted-foreground" title={question}>
            {question ? `"${question}"` : ""} {route && route !== "guard" ? `→ ${AGENT_NAME[route]} Agent` : route === "guard" ? "→ 가드레일 차단" : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button onClick={() => setReplay((n) => n + 1)} className="flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-bold text-primary hover:bg-accent" title="처음부터 다시 재생">
            <RotateCcw className="size-3.5" /> 다시 재생
          </button>
          <button onClick={onClose} aria-label="흐름 닫기" className="rounded-full p-1.5 text-muted-foreground hover:bg-[#f0f0f2]">
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* 참여 모듈 머리 */}
      <div className="relative shrink-0 px-5 pt-3" style={{ height: 64 }}>
        {parts.map((id) => {
          const p = part(id);
          return (
            <div key={id} className="absolute flex -translate-x-1/2 flex-col items-center" style={{ left: 20 + x(id), width: col - 4 }}>
              <span className="grid size-7 place-items-center rounded-full text-white shadow-sm" style={{ background: p.color }}>{p.icon}</span>
              <span className="mt-1 max-w-full truncate text-center text-[11px] leading-tight font-bold" title={p.name}>{p.name}</span>
              <span className="max-w-full truncate text-center text-[9.5px] leading-tight text-muted-foreground">{p.sub}</span>
            </div>
          );
        })}
      </div>

      {/* 단계(화살표) */}
      <div key={replay} className="relative flex-1 overflow-y-auto px-5 pb-4">
        <div className="relative" style={{ height: steps.length * ROW + 16, width: W }}>
          {/* 생명선 */}
          {parts.map((id) => (
            <div key={id} className="absolute top-0 bottom-0 border-l border-dashed" style={{ left: x(id), borderColor: `${part(id).color}55` }} />
          ))}
          {steps.map((s, i) => (
            <Step key={s.seq} s={s} i={i} x1={x(s.src)} x2={x(s.dst)} />
          ))}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-black/[0.06] px-5 py-2.5 text-[11.5px] text-muted-foreground">
        <span>단계 <b className="text-foreground">{steps.length}</b></span>
        {stats.map(([k, v]) => (
          <span key={k}>{k} <b className="text-foreground">{v}</b></span>
        ))}
        <span className="ml-auto">측정된 시간 합 <b className="font-mono text-foreground">{totalMs.toLocaleString()} ms</b></span>
      </div>
    </aside>
  );
}

function Step({ s, i, x1, x2 }: { s: TraceStep; i: number; x1: number; x2: number }) {
  const y = i * ROW + 30;
  // 생략(의도된 건너뜀, 예: API 키 없음)은 회색 점선, 실패 · 차단은 빨간색
  const skipped = !s.ok && s.label.includes("생략");
  const color = s.ok ? part(s.src).color : skipped ? "#8e8e93" : "#ff3b30";
  const bad = !s.ok && !skipped;
  const delay = `${i * STEP_DELAY}s`;
  const self = s.src === s.dst;
  const ms = s.ms != null ? <span className="ml-1 rounded bg-[#f0f0f2] px-1 font-mono text-[9.5px] font-normal text-[#6e6e73]">{s.ms} ms</span> : null;

  if (self) {
    // 자기 자신: 생명선 위의 코드 판정 단계(오른쪽에 설명)
    const right = x1 + 14;
    return (
      <div className="seq-row absolute inset-x-0" style={{ top: y - 22, height: ROW, animationDelay: delay }}>
        <svg className="absolute overflow-visible" style={{ left: 0, top: 0 }} width={1} height={1}>
          <path d={`M ${x1} 16 h 12 v 14 h -12`} fill="none" stroke={color} strokeWidth={1.6} className="seq-arrow" style={{ animationDelay: delay }} />
        </svg>
        <span className="absolute size-2 -translate-x-1/2 rounded-full" style={{ left: x1, top: 26, background: color }} />
        <div className="absolute pr-1" style={{ left: Math.min(right + 4, W - 200), top: 6, width: Math.max(200, W - right - 8) }}>
          <p className={cn("text-[11.5px] leading-tight font-bold", bad && "text-[#d70015]")}>
            {s.label}
            {ms}
          </p>
          <p className="mt-0.5 line-clamp-2 text-[10.5px] leading-snug text-[#3a3a3c]" title={s.detail}>{s.detail}</p>
        </div>
      </div>
    );
  }

  const left = Math.min(x1, x2);
  const span = Math.abs(x2 - x1);
  const dir = x2 > x1 ? 1 : -1;
  // 글자 상자: 화살표 가운데, 너비는 최소 170px(그림 밖으로 나가지 않게)
  const boxW = Math.max(span, 170);
  const boxLeft = Math.min(Math.max(left + span / 2 - boxW / 2, 0), W - boxW);
  const markerId = `arr-${s.seq}`;
  return (
    <div className="seq-row absolute inset-x-0" style={{ top: y - 22, height: ROW, animationDelay: delay }}>
      <div className="absolute text-center" style={{ left: boxLeft, width: boxW, top: 0 }}>
        <p className={cn("truncate text-[11.5px] leading-tight font-bold", bad && "text-[#d70015]")} title={s.label}>
          {s.label}
          {ms}
        </p>
      </div>
      <svg className="absolute overflow-visible" style={{ left: 0, top: 0 }} width={1} height={1}>
        <defs>
          <marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
          </marker>
        </defs>
        <line
          x1={x1 + dir * 4}
          y1={22}
          x2={x2 - dir * 6}
          y2={22}
          stroke={color}
          strokeWidth={1.8}
          strokeDasharray={s.dst === "user" || skipped ? "5 4" : undefined}
          className={s.dst === "user" || skipped ? "" : "seq-arrow"}
          style={{ animationDelay: delay }}
          markerEnd={`url(#${markerId})`}
        />
      </svg>
      <span className="absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ left: x1, top: 22, background: color }} />
      <div className="absolute text-center" style={{ left: boxLeft, width: boxW, top: 27 }}>
        <p className={cn("line-clamp-2 text-[10.5px] leading-snug", bad ? "text-[#d70015]" : skipped ? "text-[#8e8e93]" : "text-[#3a3a3c]")} title={s.detail}>{s.detail}</p>
      </div>
    </div>
  );
}
