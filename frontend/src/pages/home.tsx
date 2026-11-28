import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowRight,
  BarChart3,
  Bot,
  Boxes,
  CheckCircle2,
  FileSearch,
  KeyRound,
  Library,
  type LucideIcon,
  PackagePlus,
  Repeat,
  Server,
  ShieldCheck,
  Sparkles,
  Wrench,
  ArrowRightLeft,
  Activity,
} from "lucide-react";
import type { PageKey } from "@/App";
import type { Role } from "@/lib/sample-data";
import { useAssets, useMe, useMonitoringSummary, useSystems } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import { IsoArt } from "@/components/iso-art";
import { cn } from "@/lib/utils";

type Step = { icon: LucideIcon; title: string; sub: string; who: string; to: PageKey };

// 연계 전체 프로세스: 등록 → 구독 → 호출 → 운영
const PHASES: { no: string; en: string; title: string; color: string; tint: string; steps: Step[] }[] = [
  {
    no: "01", en: "Publish", title: "등록", color: "#ff9500", tint: "#fff6e8",
    steps: [
      { icon: Server, title: "시스템 등록", sub: "프로세스 · 담당자 · 서버", who: "시스템 담당자", to: "systems" },
      { icon: PackagePlus, title: "API · MCP 등록", sub: "API 또는 직접 개발한 MCP 서버", who: "시스템 담당자", to: "publish" },
      { icon: ArrowRightLeft, title: "API → MCP 변환", sub: "오퍼레이션을 Tool로", who: "시스템 담당자", to: "convert" },
      { icon: CheckCircle2, title: "승인 · 카탈로그 공개", sub: "저장 → 승인 → 스테이지 → 운영", who: "admin", to: "catalog" },
    ],
  },
  {
    no: "02", en: "Subscribe", title: "구독", color: "#34c759", tint: "#ecf9ef",
    steps: [
      { icon: Library, title: "카탈로그에서 찾기", sub: "API · MCP 서버 검색", who: "누구나", to: "catalog" },
      { icon: Repeat, title: "시스템 구독", sub: "Agent 시스템 → 대상 MCP · API", who: "Agent 담당자", to: "subscriptions" },
      { icon: KeyRound, title: "Tool 사용 신청", sub: "카탈로그에서 Tool별로", who: "개인 사용자", to: "catalog" },
      { icon: CheckCircle2, title: "프로바이더 승인", sub: "대상 시스템 담당자가 승인", who: "시스템 담당자", to: "subscriptions" },
    ],
  },
  {
    no: "03", en: "Run", title: "호출", color: "#0071e3", tint: "#eaf3fd",
    steps: [],
  },
  {
    no: "04", en: "Observe", title: "운영", color: "#ff3b30", tint: "#fdeeed",
    steps: [
      { icon: Activity, title: "API 사용내역", sub: "트랜잭션별 상세 추적", who: "담당자", to: "usage-api" },
      { icon: Bot, title: "MCP 사용내역", sub: "사용자 · Tool별 호출", who: "누구나", to: "usage-mcp" },
      { icon: BarChart3, title: "호출 통계", sub: "일별 · 월별 추이", who: "담당자", to: "stats" },
      { icon: Wrench, title: "오류 조치", sub: "규칙 분류 + Agent 분석", who: "담당자", to: "usage-api" },
    ],
  },
];

const AGENT_HELP = [
  { icon: FileSearch, text: "연계 방식 컨설팅 · 입력란 자동 채움" },
  { icon: Sparkles, text: "구독 · Tool 신청 대행" },
  { icon: ShieldCheck, text: "판정은 규칙 코드, 설명은 LLM" },
  { icon: Wrench, text: "오류 원인 분석 · 조치 안내" },
];

const GATE_CHECKS = ["인증", "구독 확인", "Tool 권한", "가드레일"];

export function HomePage({ role, onNavigate, onAskAgent }: { role: Role; onNavigate: (p: PageKey) => void; onAskAgent: () => void }) {
  const me = useMe().data!;
  const assets = useAssets().data ?? [];
  const live = assets.filter((a) => a.status === "LIVE");
  const agents = (useSystems({ kind: "AGENT" }).data ?? []).length;
  const links = assets.reduce((n, a) => n + a.subscriber_count, 0); // 승인된 시스템 구독 수
  const summary = useMonitoringSummary().data;
  const canPublish = role !== "일반 사용자";
  const go = (p: PageKey) => {
    // 역할상 열 수 없는 화면이면 카탈로그로 보낸다
    const managerOnly: PageKey[] = ["publish", "convert", "subscriptions", "usage-api", "stats"];
    onNavigate(!canPublish && managerOnly.includes(p) ? "catalog" : p);
  };

  return (
    <div className="space-y-8">
      {/* ===== 히어로 ===== */}
      <section className="relative overflow-hidden rounded-[28px] bg-white px-12 py-12 shadow-[0_20px_60px_rgb(0_0_0/0.06),0_0_0_1px_rgb(0_0_0/0.03)]">
        <div className="pointer-events-none absolute -top-40 -left-40 size-[620px] rounded-full bg-[radial-gradient(closest-side,rgb(0_113_227/0.12),transparent)]" />
        <div className="pointer-events-none absolute -right-32 -bottom-48 size-[560px] rounded-full bg-[radial-gradient(closest-side,rgb(125_92_245/0.12),transparent)]" />
        <div className="relative grid items-center gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
          <div>
            <span className="inline-block rounded-full bg-[#e8f2fd] px-3.5 py-1.5 text-[13px] font-bold text-[#0066cc] ring-1 ring-[#b7d6f8]">
              AI-to-X 연계 거버넌스 플랫폼
            </span>
            <h1 className="mt-6 text-[60px] leading-[1.08] font-extrabold tracking-[-0.04em]">
              Connect every AI
              <br />
              to everything, <span className="grad-text">safely.</span>
            </h1>
            <p className="mt-5 max-w-xl text-[18px] leading-relaxed text-[#3a3a3c]">
              사내 시스템을 API · MCP로 등록하고, AI Agent가 승인된 Tool만 안전하게 호출하도록. 등록부터 구독, 호출, 운영까지 한 곳에서 관리합니다.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button onClick={() => onNavigate("catalog")} className="h-12 px-6 text-[15px]">
                카탈로그 둘러보기 <ArrowRight />
              </Button>
              {canPublish ? (
                <Button variant="outline" onClick={() => onNavigate("publish")} className="h-12 px-6 text-[15px]">
                  API 등록하기
                </Button>
              ) : (
                <Button variant="outline" onClick={() => onNavigate("systems")} className="h-12 px-6 text-[15px]" title="시스템을 등록하면 담당자가 되어 API · MCP 등록과 승인을 할 수 있습니다">
                  시스템 등록하기
                </Button>
              )}
              <Button variant="ghost" onClick={onAskAgent} className="h-12 px-5 text-[15px]">
                <Bot /> Agent에게 물어보기
              </Button>
            </div>
          </div>

          <IsoArt className="w-full max-w-[470px] lg:-ml-10" />
        </div>

        <div className="relative mt-10 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="운영 중 API · MCP" value={live.length} sub={`API ${live.filter((a) => a.type === "API").length} · MCP ${live.filter((a) => a.type === "MCP").length}`} />
          <Stat label="AI Agent 시스템" value={agents} sub="시스템 단위로 관리" />
          <Stat label="활성 연계" value={links} sub="승인된 시스템 구독" />
          <Stat label="오늘 호출" value={(summary?.today_calls ?? 0).toLocaleString()} sub={`오류율 ${(summary?.today_error_rate ?? 0).toFixed(2)}% · 내 조회 범위`} />
        </div>
      </section>

      {/* ===== 연계 전체 프로세스 ===== */}
      <section className="rounded-[28px] bg-white p-10 shadow-[0_20px_60px_rgb(0_0_0/0.06),0_0_0_1px_rgb(0_0_0/0.03)]">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[14px] font-bold text-primary">How it works</p>
            <h2 className="mt-1 text-[34px] font-extrabold tracking-[-0.035em]">연계 전체 프로세스</h2>
            <p className="mt-1.5 text-[16px] text-muted-foreground">등록 → 구독 → 호출 → 운영. 단계를 누르면 해당 화면으로 이동합니다.</p>
          </div>
          <div className="flex flex-wrap gap-2 text-[12.5px]">
            <Legend color="#ff9500">프로바이더</Legend>
            <Legend color="#34c759">컨슈머</Legend>
            <Legend color="#0071e3">Data plane</Legend>
            <Legend color="#ff3b30">운영</Legend>
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_28px_minmax(0,1fr)_28px_minmax(0,1fr)_28px_minmax(0,1fr)] items-stretch">
          {PHASES.map((ph, i) => (
            <PhaseWithArrow key={ph.no} last={i === PHASES.length - 1} color={ph.color}>
              <div className="flex h-full flex-col rounded-[22px] p-4" style={{ background: ph.tint }}>
                <div className="mb-3 flex items-center gap-2.5 px-1">
                  <span className="grid size-9 place-items-center rounded-full text-[13px] font-extrabold text-white" style={{ background: ph.color }}>
                    {ph.no}
                  </span>
                  <div>
                    <p className="text-[11px] font-bold tracking-wide uppercase" style={{ color: ph.color }}>{ph.en}</p>
                    <p className="text-[19px] leading-tight font-extrabold tracking-[-0.03em]">{ph.title}</p>
                  </div>
                </div>
                {ph.steps.length > 0 ? (
                  <div className="flex flex-1 flex-col gap-2">
                    {ph.steps.map((s, k) => (
                      <button
                        key={s.title}
                        onClick={() => go(s.to)}
                        className="group flex flex-1 items-center gap-3 rounded-2xl bg-white px-3 py-2.5 text-left shadow-[0_1px_2px_rgb(0_0_0/0.04)] ring-1 ring-black/[0.04] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
                      >
                        <span className="grid size-9 shrink-0 place-items-center rounded-xl" style={{ background: ph.tint, color: ph.color }}>
                          <s.icon className="size-[18px]" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-1.5 text-[14px] font-bold tracking-[-0.01em]">
                            <span className="text-[11px] font-extrabold" style={{ color: ph.color }}>{k + 1}</span>
                            {s.title}
                          </span>
                          <span className="block truncate text-[11.5px] text-muted-foreground">{s.sub}</span>
                        </span>
                        <span className="hidden shrink-0 rounded-full bg-[#f0f0f2] px-2 py-0.5 text-[10.5px] font-bold text-[#6e6e73] xl:inline">{s.who}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <RuntimeFlow />
                )}
              </div>
            </PhaseWithArrow>
          ))}
        </div>

        {/* A2X Agent 띠: 단계마다 Agent가 돕는 일 */}
        <div className="mt-4 grid grid-cols-[minmax(0,1fr)_28px_minmax(0,1fr)_28px_minmax(0,1fr)_28px_minmax(0,1fr)] overflow-hidden rounded-[20px] bg-gradient-to-r from-[#2f6bff] via-[#7d5cf5] to-[#bf5af2] text-white">
          {AGENT_HELP.map((h, i) => (
            <div key={h.text} className={cn("flex items-center gap-2.5 px-4 py-3.5", i > 0 && "col-start-auto", i < AGENT_HELP.length - 1 && "col-span-2")}>
              {i === 0 && (
                <span className="mr-1 flex shrink-0 items-center gap-1.5 rounded-full bg-white/20 px-2.5 py-1 text-[12px] font-extrabold">
                  <Bot className="size-3.5" /> A2X Agent
                </span>
              )}
              <h.icon className="size-4 shrink-0 text-white/90" />
              <span className="text-[13px] font-medium">{h.text}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ===== 바로 시작하기 ===== */}
      <section>
        <h2 className="mb-4 text-[24px] font-extrabold tracking-[-0.03em]">{me.user.name} 님, 바로 시작하기</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {(canPublish
            ? [
                { icon: PackagePlus, title: "API를 등록하고 MCP로 열기", desc: "Swagger · 엑셀로 레이아웃을 가져오고, 오퍼레이션을 MCP Tool로 변환합니다.", to: "publish" as PageKey, color: "#ff9500" },
                { icon: Repeat, title: "들어온 신청 승인하기", desc: "내 시스템을 대상으로 한 시스템 구독과 Tool 사용 신청을 처리합니다.", to: "subscriptions" as PageKey, color: "#34c759" },
                { icon: Activity, title: "실패한 호출 살펴보기", desc: "트랜잭션 상세에서 원인을 보고 오류 조치 Agent에 분석을 맡깁니다.", to: "usage-api" as PageKey, color: "#ff3b30" },
              ]
            : [
                { icon: Library, title: "필요한 Tool 찾기", desc: "카탈로그에서 MCP 서버를 찾고 바로 Tool 사용을 신청합니다.", to: "catalog" as PageKey, color: "#34c759" },
                { icon: KeyRound, title: "내 Tool 권한 확인", desc: "승인된 Tool과 진행 중인 신청을 확인합니다.", to: "my-access" as PageKey, color: "#0071e3" },
                { icon: Bot, title: "내 호출 내역 보기", desc: "내가 Agent로 호출한 Tool과 결과를 확인합니다.", to: "usage-mcp" as PageKey, color: "#7d5cf5" },
              ]
          ).map((c) => (
            <button
              key={c.title}
              onClick={() => onNavigate(c.to)}
              className="group rounded-[22px] bg-white p-6 text-left shadow-[0_20px_60px_rgb(0_0_0/0.05),0_0_0_1px_rgb(0_0_0/0.03)] transition-all duration-300 hover:-translate-y-1"
            >
              <span className="grid size-11 place-items-center rounded-[13px] text-white" style={{ background: c.color }}>
                <c.icon className="size-5" />
              </span>
              <p className="mt-4 text-[18px] font-extrabold tracking-[-0.02em]">{c.title}</p>
              <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">{c.desc}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-[13.5px] font-bold text-primary">
                바로가기 <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: ReactNode; sub: string }) {
  return (
    <div className="rounded-[20px] bg-[#f5f6f8] p-5">
      <p className="text-[13px] text-muted-foreground">{label}</p>
      <p className="mt-1.5 text-[34px] leading-none font-extrabold tracking-[-0.03em]">{value}</p>
      <p className="mt-2 text-[12px] text-muted-foreground">{sub}</p>
    </div>
  );
}

function Legend({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="flex items-center gap-1.5 rounded-full bg-[#f5f6f8] px-3 py-1 font-medium">
      <span className="size-2 rounded-full" style={{ background: color }} />
      {children}
    </span>
  );
}

// 단계 사이 화살표: 점이 오른쪽으로 흘러간다
function PhaseWithArrow({ children, last, color }: { children: ReactNode; last: boolean; color: string }) {
  return (
    <>
      {children}
      {!last && (
        <div className="relative flex items-center justify-center">
          <div className="h-[2px] w-full bg-[repeating-linear-gradient(90deg,#c7c7cc_0_4px,transparent_4px_8px)]" />
          <span className="flow-x absolute top-1/2 left-0 size-2 -translate-y-1/2 rounded-full" style={{ background: color }} />
          <ArrowRight className="absolute size-4 text-[#8e8e93]" />
        </div>
      )}
    </>
  );
}

// ③ 호출 단계 그림: AI Agent → A2X Gateway(검사 4단계) → API · MCP 서버
function RuntimeFlow() {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setActive((a) => (a + 1) % (GATE_CHECKS.length + 2)), 700);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex flex-1 flex-col items-stretch">
      <RunNode icon={Bot} title="AI Agent" sub="CS 챗봇 · 사용자 홍길동" />
      <FlowDown />
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#1d1d1f] to-[#2c2c54] p-3.5 text-white shadow-[0_10px_30px_rgb(47_107_255/0.25)]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(260px_120px_at_20%_0%,rgb(47_107_255/0.45),transparent)]" />
        <div className="relative">
          <p className="flex items-center gap-2 text-[14px] font-extrabold tracking-[-0.01em]">
            <ShieldCheck className="size-4 text-[#7fb2ff]" /> A2X Gateway
          </p>
          <div className="mt-2.5 grid grid-cols-2 gap-1.5">
            {GATE_CHECKS.map((c, i) => {
              const passed = active > i;
              return (
                <span
                  key={c}
                  className={cn(
                    "flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-bold whitespace-nowrap transition-all duration-300",
                    passed ? "bg-[#34c759]/25 text-[#9ff0b4]" : active === i ? "bg-white/20 text-white" : "bg-white/[0.07] text-white/50",
                  )}
                >
                  <CheckCircle2 className={cn("size-3.5", passed ? "opacity-100" : "opacity-40")} />
                  {c}
                </span>
              );
            })}
          </div>
        </div>
      </div>
      <FlowDown />
      <RunNode icon={Boxes} title="API · MCP 서버" sub="승인된 Tool만 호출" highlight={active === GATE_CHECKS.length + 1} />
    </div>
  );
}

function RunNode({ icon: Icon, title, sub, highlight }: { icon: LucideIcon; title: string; sub: string; highlight?: boolean }) {
  return (
    <div className={cn("flex items-center gap-3 rounded-2xl bg-white px-3 py-2.5 ring-1 transition-all duration-300", highlight ? "ring-2 ring-[#34c759]" : "ring-black/[0.04]")}>
      <span className="grid size-9 place-items-center rounded-xl bg-[#eaf3fd] text-primary">
        <Icon className="size-[18px]" />
      </span>
      <span>
        <span className="block text-[14px] font-bold">{title}</span>
        <span className="block text-[11.5px] text-muted-foreground">{sub}</span>
      </span>
    </div>
  );
}

function FlowDown() {
  return (
    <div className="relative mx-auto h-7 w-[2px] bg-[repeating-linear-gradient(180deg,#9ec5f5_0_4px,transparent_4px_8px)]">
      <span className="flow-y absolute left-1/2 size-2 -translate-x-1/2 rounded-full bg-primary shadow-[0_0_8px_#0071e3]" />
    </div>
  );
}
