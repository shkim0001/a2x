import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Loader2,
  LogOut,
  ArrowRightLeft,
  BarChart3,
  Bot,
  ChevronRight,
  FileText,
  HardDrive,
  Home,
  KeyRound,
  LayoutDashboard,
  Library,
  PackagePlus,
  Repeat,
  Server,
  ServerCog,
  MonitorCheck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchHealth, get, post, put, type FormSuggestion, type StoredRole, type Me } from "@/lib/api";
import { AgentBridgeContext, type AgentBridge, type AgentFocus, type EditRequest } from "@/lib/agent-bridge";
import type { Role } from "@/lib/sample-data";
import { ROLE } from "@/lib/labels";
import { useInstances, useMe, useMonitoringSummary, useSubscriptions, useSystems, useToolRequests } from "@/lib/queries";
import { LoginPage } from "@/pages/login";
import { Button } from "@/components/ui/button";
import { AgentPanel } from "@/components/agent-panel";
import { HomePage } from "@/pages/home";
import { DashboardPage } from "@/pages/dashboard";
import { SystemsPage } from "@/pages/systems";
import { ServersPage } from "@/pages/servers";
import { CatalogPage } from "@/pages/catalog";
import { PublishPage } from "@/pages/publish";
import { McpRegisterPage } from "@/pages/mcp-register";
import { ConvertPage } from "@/pages/convert";
import { SubscriptionsPage } from "@/pages/subscriptions";
import { MyAccessPage } from "@/pages/my-access";
import { ApiUsagePage, CallStatsPage, McpUsagePage } from "@/pages/monitoring";
import { InstancesPage } from "@/pages/instances";
import { DocsPage } from "@/pages/docs";

export type PageKey =
  | "home"
  | "dashboard"
  | "systems"
  | "servers"
  | "catalog"
  | "publish"
  | "mcp-register"
  | "convert"
  | "subscriptions"
  | "my-access"
  | "usage-api"
  | "usage-mcp"
  | "instances"
  | "stats"
  | "docs";

type GroupKey = "home" | "master" | "register" | "access" | "monitoring" | "admin";

const ALL: Role[] = ["일반 사용자", "시스템 담당자", "admin"];
const MANAGER: Role[] = ["시스템 담당자", "admin"];

// 상단 대메뉴 (덱의 목차 탭 스타일)
const GROUPS: { key: GroupKey; label: string; sub: string; color: string }[] = [
  { key: "home", label: "홈", sub: "메인 · 대시보드", color: "#0071e3" },
  { key: "master", label: "기준정보", sub: "시스템 · 서버", color: "#5e5ce6" },
  { key: "register", label: "카탈로그 등록", sub: "API · MCP 등록 · 변환", color: "#ff9500" },
  { key: "access", label: "구독 · 권한", sub: "찾기 · 신청 · 승인", color: "#34c759" },
  { key: "monitoring", label: "모니터링", sub: "사용내역 · 통계", color: "#ff3b30" },
  { key: "admin", label: "관리", sub: "admin", color: "#8e8e93" },
];

// 왼쪽 하위 메뉴
const PAGES: { key: PageKey; group: GroupKey; label: string; sub: string; desc: string; icon: LucideIcon; roles: Role[] }[] = [
  { key: "home", group: "home", label: "메인", sub: "전체 프로세스", desc: "", icon: Home, roles: ALL },
  { key: "dashboard", group: "home", label: "대시보드", sub: "한눈에 보기", desc: "승인할 요청, 내 권한, 최근 오류를 한 화면에서 확인합니다.", icon: LayoutDashboard, roles: ALL },
  { key: "systems", group: "master", label: "시스템", sub: "담당자 · 프로세스", desc: "모든 연계는 시스템 단위로 관리합니다. AI Agent도 하나의 시스템입니다.", icon: Server, roles: ALL },
  { key: "servers", group: "master", label: "서버", sub: "호스트 · IP · 환경", desc: "시스템을 구성하는 서버를 한 곳에서 봅니다. Gateway 연동과 방화벽 신청의 기준 정보입니다.", icon: HardDrive, roles: ALL },
  { key: "publish", group: "register", label: "API 등록", sub: "업무 · 레이아웃 · 리소스", desc: "시스템의 API를 등록합니다. 저장 → 승인 → 스테이지 → 운영 순서로 진행됩니다.", icon: PackagePlus, roles: MANAGER },
  { key: "mcp-register", group: "register", label: "MCP 등록", sub: "직접 개발한 MCP 서버", desc: "타겟 시스템이 직접 개발 · 운영하는 MCP 서버를 등록합니다. 연결 정보와 공개할 Tool을 정의합니다.", icon: ServerCog, roles: MANAGER },
  { key: "convert", group: "register", label: "MCP 변환", sub: "API → Tool", desc: "등록된 API를 MCP Tool로 변환해 AI Agent가 쓸 수 있게 엽니다.", icon: ArrowRightLeft, roles: MANAGER },
  { key: "catalog", group: "access", label: "카탈로그", sub: "API · MCP 찾기", desc: "운영 중인 API와 MCP 서버를 찾고 바로 사용 신청합니다.", icon: Library, roles: ALL },
  { key: "subscriptions", group: "access", label: "구독 · 승인", sub: "시스템 · Tool", desc: "① 시스템 구독과 ② Tool 사용 신청을 대상 시스템 담당자(또는 admin)가 승인합니다.", icon: Repeat, roles: MANAGER },
  { key: "my-access", group: "access", label: "내 권한", sub: "신청 현황", desc: "내가 신청한 MCP Tool의 승인 상태를 보고 취소 · 해지합니다. 새 Tool은 카탈로그에서 신청합니다.", icon: KeyRound, roles: ALL },
  { key: "usage-api", group: "monitoring", label: "API 사용내역", sub: "트랜잭션", desc: "API 호출 트랜잭션을 조회합니다. Status를 누르면 상세 내용을 볼 수 있습니다.", icon: Activity, roles: MANAGER },
  { key: "usage-mcp", group: "monitoring", label: "MCP 사용내역", sub: "Tool 호출", desc: "MCP Tool 호출 내역을 조회합니다. 사용자별 권한 거부도 함께 보입니다.", icon: Bot, roles: ALL },
  { key: "stats", group: "monitoring", label: "호출 통계", sub: "일별 · 월별", desc: "일별 · 월별 API · MCP 호출량, 오류율, 평균 응답시간을 봅니다.", icon: BarChart3, roles: MANAGER },
  { key: "instances", group: "monitoring", label: "인스턴스 모니터링", sub: "구성요소 상태", desc: "포탈 · 권한 Gateway · MCP/API Gateway · MCP 서버 · 외부 MCP · Agent · 운영 데이터가 정상인지 봅니다. 비정상은 맨 위에 바로 표시됩니다.", icon: MonitorCheck, roles: MANAGER },
  { key: "docs", group: "admin", label: "컨설팅 문서", sub: "admin", desc: "컨설팅 Agent가 답변 근거로 쓰는 사내 문서를 관리합니다.", icon: FileText, roles: ["admin"] },
];

// 로그인 확인: 로그인 전에는 포탈을 보여주지 않는다
export default function App() {
  const me = useMe();
  if (me.isLoading) {
    return (
      <div className="grid min-h-screen place-items-center text-muted-foreground">
        <Loader2 className="size-6 animate-spin" />
      </div>
    );
  }
  if (me.isError) {
    return <div className="grid min-h-screen place-items-center text-sm text-[#d70015]">백엔드에 연결할 수 없습니다. 포탈 API(8000)가 실행 중인지 확인하세요.</div>;
  }
  if (!me.data) return <LoginPage />;
  return <Portal me={me.data} />;
}

// Agent 양식 제안 → 해당 양식 화면
const FORM_PAGE: Record<FormSuggestion["form"], PageKey> = { api: "publish", mcp: "mcp-register", subscription: "catalog", system: "systems", server: "servers", system_servers: "systems" };

// 라우터 라이브러리는 아직 승인 전이라 상태로 화면을 전환한다.
function Portal({ me }: { me: Me }) {
  const qc = useQueryClient();
  const [page, setPageRaw] = useState<PageKey>("home");
  // 역할은 서버가 계산한다: admin > 담당 시스템이 있으면 시스템 담당자 > 일반 사용자
  const role: Role = ROLE[me.effective_role];
  const [agentOpen, setAgentOpen] = useState(false);
  // Agent 연결: 화면 문맥(선택한 자산 · 트랜잭션), 양식 제안, 화면에서 보낸 질문
  const [focus, setFocus] = useState<AgentFocus>({});
  const [suggestion, setSuggestion] = useState<FormSuggestion | null>(null);
  const [editing, setEditing] = useState<EditRequest | null>(null);
  const [requesting, setRequesting] = useState<number[] | null>(null);
  const [pendingAsk, setPendingAsk] = useState<{ id: number; text: string } | null>(null);
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  const pages = PAGES.filter((p) => p.roles.includes(role));
  const current = pages.find((p) => p.key === page) ?? pages[0];
  const group = GROUPS.find((g) => g.key === current.group)!;
  // 트리는 처음엔 접힌 상태(현재 그룹인 '홈'만 펼침). 다른 메뉴로 가면 그 그룹을 펼친다.
  const [collapsed, setCollapsed] = useState<Set<GroupKey>>(
    () => new Set(GROUPS.map((g) => g.key).filter((k) => k !== "home")),
  );
  const setPage = (k: PageKey) => {
    setPageRaw(k);
    setFocus({});
    const g = PAGES.find((p) => p.key === k)?.group;
    if (g)
      setCollapsed((c) => {
        if (!c.has(g)) return c;
        const n = new Set(c);
        n.delete(g);
        return n;
      });
  };
  const toggleGroup = (g: GroupKey) =>
    setCollapsed((c) => {
      const n = new Set(c);
      if (n.has(g)) n.delete(g);
      else n.add(g);
      return n;
    });

  // 로그아웃: 세션을 끊고 페이지를 새로 열어 로그인 화면으로(화면에 남은 데이터 · 상태를 모두 버린다)
  const logout = async () => {
    await post("/auth/logout").catch(() => undefined);
    qc.clear();
    window.location.replace("/");
  };

  // 개발용 권한 스위치(서버가 개발 환경에서만 켜 준다). 담당 시스템이 있어도 일반 사용자로 바꿔 쓸 수 있다
  const devSwitch = useQuery({ queryKey: ["auth-providers"], queryFn: () => get<{ google: boolean; dev_role_switch: boolean }>("/auth/providers") }).data?.dev_role_switch;
  const switchRole = async (want: StoredRole) => {
    const next = await put<Me>("/auth/dev/role", { role: want });
    qc.setQueryData(["me"], next);
    await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  };
  const openGroup = (g: GroupKey) => setPage(pages.find((p) => p.group === g)!.key);

  // ---- 왼쪽 패널용 집계 (실제 API) ----
  const mySystems = useSystems({ mine: true }).data ?? [];
  const pendingSubs = useSubscriptions({ scope: "approve", status: "PENDING" }).data ?? [];
  const pendingTools = useToolRequests({ scope: "approve", status: "PENDING" }).data ?? [];
  const myRequests = useToolRequests({ scope: "mine", status: "PENDING" }).data ?? [];
  const toApprove = role === "일반 사용자" ? 0 : pendingSubs.length + pendingTools.length;
  const myPending = myRequests.length;
  // 실패한 호출: 내 조회 범위의 최근 24시간 실패 건수(서버 집계)
  const myFails = useMonitoringSummary().data?.failed_24h ?? 0;
  // 인스턴스 모니터링: 비정상 구성요소 수를 메뉴 배지로(시스템 담당자 · admin)
  const instDown = useInstances(true, role !== "일반 사용자").data?.counts.down ?? 0;
  const badge: Partial<Record<PageKey, number>> = { subscriptions: toApprove, "my-access": myPending, instances: instDown };

  const clearSuggestion = useCallback(() => setSuggestion(null), []);
  const clearEdit = useCallback(() => setEditing(null), []);
  const clearRequest = useCallback(() => setRequesting(null), []);
  const bridge = useMemo<AgentBridge>(
    () => ({
      focus,
      setFocus,
      ask: (message: string) => {
        setAgentOpen(true);
        setPendingAsk({ id: Date.now(), text: message });
      },
      suggestion,
      apply: (s: FormSuggestion) => {
        setSuggestion(s);
        setPage(FORM_PAGE[s.form]); // 트리 펼침 포함
      },
      clear: clearSuggestion,
      editing,
      edit: (r: EditRequest) => {
        setEditing(r);
        setPage(r.type === "API" ? "publish" : "mcp-register");
      },
      clearEdit,
      requesting,
      request: (ids: number[]) => {
        setRequesting(ids);
        setPage("catalog");
      },
      clearRequest,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [focus, suggestion, clearSuggestion, editing, clearEdit, requesting, clearRequest],
  );

  return (
    <AgentBridgeContext.Provider value={bridge}>
    <div className="relative min-h-screen">
      <div className="orb left-[-140px] top-[300px] size-[520px] bg-[#cfe0ff]" />
      <div className="orb right-[-160px] top-[-120px] size-[560px] bg-[#e6dcff] [animation-delay:-6s]" />
      <div className="orb bottom-[-220px] left-[40%] size-[420px] bg-[#d6f5dd] [animation-delay:-11s]" />

      {/* ===== 상단 바: 대메뉴 ===== */}
      <header className="sticky top-0 z-30 border-b border-black/[0.08] bg-white/70 backdrop-blur-xl backdrop-saturate-[1.8]">
        <div className="flex h-[76px] items-center gap-5 px-5">
          <button onClick={() => setPage("home")} className="group flex w-[244px] shrink-0 items-center gap-2.5" aria-label="A2X Portal 메인으로">
            <img src="/favicon.svg" alt="" className="size-[34px] rounded-[10px] shadow-[0_6px_16px_rgb(47_107_255/0.35)] transition-transform duration-300 group-hover:rotate-[-6deg]" />
            {/* 제목과 부제를 거의 붙여 한 덩어리로 보이게 한다 */}
            <span className="text-left">
              <span className="flex items-baseline gap-1.5 text-[20px] leading-[20px] tracking-[-0.045em]">
                <b className="font-extrabold text-[#1d1d1f]">A2X</b>
                <span className="font-medium text-[#6e6e73]">Portal</span>
              </span>
              <small className="block text-[11.5px] leading-[13px] tracking-[-0.01em] text-muted-foreground">AI 연계 거버넌스</small>
            </span>
          </button>

          {/* 박스 없는 글자 메뉴: 선택된 메뉴만 진한 글자 + 파란 밑줄 */}
          <nav className="flex h-full min-w-0 flex-1 items-stretch gap-1">
            {GROUPS.filter((g) => pages.some((p) => p.group === g.key)).map((g) => {
              const on = g.key === group.key;
              return (
                <button
                  key={g.key}
                  onClick={() => openGroup(g.key)}
                  className={cn(
                    "group relative px-5 text-[16px] tracking-[-0.02em] transition-colors duration-200",
                    on ? "font-bold text-foreground" : "font-medium text-[#6e6e73] hover:text-foreground",
                  )}
                >
                  {g.label}
                  <span
                    className={cn(
                      "absolute right-5 bottom-0 left-5 h-[3px] rounded-t-full bg-primary transition-all duration-300",
                      on ? "opacity-100" : "scale-x-0 opacity-0 group-hover:scale-x-50 group-hover:opacity-30",
                    )}
                  />
                </button>
              );
            })}
          </nav>

          <div className="flex shrink-0 items-center gap-2.5">
            <Button size="sm" variant={agentOpen ? "secondary" : "default"} onClick={() => setAgentOpen((v) => !v)} className="h-9">
              <Bot /> Agent
            </Button>
            <div className="flex items-center gap-2 rounded-full bg-[#f0f0f2] py-1 pr-1 pl-1">
              <div className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-[#2f6bff] to-[#7d5cf5] text-[13px] font-bold text-white">
                {me.user.name[0]}
              </div>
              <span className="text-left leading-tight">
                <span className="block text-[13px] font-bold">{me.user.name}</span>
                {devSwitch ? (
                  <select
                    value={me.effective_role === "ADMIN" ? "ADMIN" : "USER"}
                    onChange={(e) => switchRole(e.target.value as StoredRole)}
                    title="개발용 권한 스위치(개발 환경에서만 보임). 시스템 담당자는 담당 시스템이 있으면 자동으로 됩니다."
                    aria-label="권한 바꾸기(개발용)"
                    className="-ml-0.5 cursor-pointer rounded bg-transparent text-[11px] text-[#5e3ce6] outline-none hover:bg-white"
                  >
                    <option value="USER">{me.effective_role === "MANAGER" ? ROLE.MANAGER : ROLE.USER}</option>
                    <option value="ADMIN">{ROLE.ADMIN}</option>
                  </select>
                ) : (
                  <span className="block text-[11px] text-muted-foreground">{role}</span>
                )}
              </span>
              <button onClick={logout} title="로그아웃" aria-label="로그아웃" className="ml-1 grid size-8 place-items-center rounded-full text-muted-foreground hover:bg-white hover:text-foreground">
                <LogOut className="size-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className={cn("relative z-10 flex gap-6 px-5 pt-6 pb-16 transition-[padding] duration-300", agentOpen && "pr-[420px]")}>
        {/* ===== 왼쪽: 하위 메뉴 + 내 할 일 ===== */}
        <aside className="sticky top-[100px] flex h-[calc(100vh-124px)] w-[244px] shrink-0 flex-col gap-4 overflow-y-auto [scrollbar-width:none]">
          {/* 전체 메뉴 트리: 대메뉴는 기본 펼침, 눌러서 접기 */}
          <nav className="rounded-[22px] bg-white/80 p-2.5 shadow-[0_20px_60px_rgb(0_0_0/0.05),0_0_0_1px_rgb(0_0_0/0.03)] backdrop-blur-xl">
            {GROUPS.filter((g) => pages.some((p) => p.group === g.key)).map((g) => {
              const children = pages.filter((p) => p.group === g.key);
              const open = !collapsed.has(g.key);
              const activeGroup = g.key === group.key;
              const groupBadge = children.reduce((s, p) => s + (badge[p.key] ?? 0), 0);
              return (
                <div key={g.key} className="py-0.5">
                  <button
                    onClick={() => toggleGroup(g.key)}
                    aria-expanded={open}
                    className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left hover:bg-[#f5f6f8]"
                  >
                    <ChevronRight className={cn("size-3.5 text-muted-foreground transition-transform duration-200", open && "rotate-90")} />
                    <span className="size-[7px] rounded-full" style={{ background: g.color }} />
                    <span className={cn("flex-1 text-[14px] font-bold tracking-[-0.01em]", activeGroup ? "text-foreground" : "text-[#3a3a3c]")}>{g.label}</span>
                    {!open && groupBadge > 0 && <span className="rounded-full bg-[#ff3b30] px-1.5 text-[11px] leading-[18px] font-bold text-white">{groupBadge}</span>}
                  </button>
                  {open && (
                    <div className="relative mt-0.5 mb-1 ml-[17px] space-y-0.5 border-l border-black/[0.08] pl-2.5">
                      {children.map((p) => {
                        const on = p.key === current.key;
                        const n = badge[p.key];
                        return (
                          <button
                            key={p.key}
                            onClick={() => setPage(p.key)}
                            className={cn(
                              "relative flex w-full items-center gap-2.5 rounded-xl px-2.5 py-[7px] text-left text-[13.5px] transition-colors duration-150",
                              on ? "bg-accent font-bold text-[#0058b9]" : "text-[#3a3a3c] hover:bg-[#f5f6f8]",
                            )}
                          >
                            {on && <span className="absolute top-1.5 bottom-1.5 -left-[11px] w-[3px] rounded-full bg-primary" />}
                            <p.icon className={cn("size-4 shrink-0", on ? "text-primary" : "text-muted-foreground")} />
                            <span className="flex-1 truncate">{p.label}</span>
                            {!!n && <span className="rounded-full bg-[#ff3b30] px-1.5 text-[11px] leading-[18px] font-bold text-white">{n}</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>

          <div className="rounded-[22px] bg-white/80 p-4 shadow-[0_20px_60px_rgb(0_0_0/0.05),0_0_0_1px_rgb(0_0_0/0.03)] backdrop-blur-xl">
            <p className="mb-3 text-[12px] font-bold text-muted-foreground">내 할 일</p>
            <div className="space-y-1">
              {[
                ...(role !== "일반 사용자" ? [{ label: "승인할 요청", n: toApprove, to: "subscriptions" as PageKey, tone: "text-[#b06d00] bg-[#fff3e0]" }] : []),
                { label: "진행 중인 내 신청", n: myPending, to: "my-access" as PageKey, tone: "text-[#0066cc] bg-[#e8f2fd]" },
                { label: "실패한 호출", n: myFails, to: (role === "일반 사용자" ? "usage-mcp" : "usage-api") as PageKey, tone: "text-[#d70015] bg-[#fdecee]" },
              ].map((t) => (
                <button key={t.label} onClick={() => setPage(t.to)} className="flex w-full items-center justify-between rounded-xl px-2 py-1.5 text-[13.5px] hover:bg-[#f5f6f8]">
                  {t.label}
                  <span className={cn("min-w-7 rounded-full px-2 text-center text-[12px] leading-5 font-bold", t.tone)}>{t.n}</span>
                </button>
              ))}
            </div>
          </div>

          {mySystems.length > 0 && role !== "일반 사용자" && (
            <div className="rounded-[22px] bg-white/80 p-4 shadow-[0_20px_60px_rgb(0_0_0/0.05),0_0_0_1px_rgb(0_0_0/0.03)] backdrop-blur-xl">
              <p className="mb-3 text-[12px] font-bold text-muted-foreground">내 시스템</p>
              <div className="space-y-1">
                {mySystems.map((s) => (
                  <button key={s.id} onClick={() => setPage("systems")} className="flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left hover:bg-[#f5f6f8]">
                    <span className={cn("grid size-7 place-items-center rounded-lg", s.kind === "AGENT" ? "bg-[#f1ecff] text-[#6e4ff6]" : "bg-[#e8f2fd] text-[#0066cc]")}>
                      {s.kind === "AGENT" ? <Bot className="size-4" /> : <Server className="size-4" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-bold">{s.name}</span>
                      <span className="block text-[11px] text-muted-foreground">{s.code !== s.name && `${s.code} · `}{s.process}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-auto flex items-center gap-2 px-3 text-[12px] text-muted-foreground">
            <span
              className={cn(
                "size-2 rounded-full ring-4",
                health.isSuccess ? "bg-[#34c759] ring-[#34c759]/15" : health.isError ? "bg-[#ff3b30] ring-[#ff3b30]/15" : "bg-[#ff9500] ring-[#ff9500]/15",
              )}
            />
            백엔드 {health.isSuccess ? `연결됨 · v${health.data.version}` : health.isError ? "연결 안 됨" : "확인 중"}
          </div>
        </aside>

        {/* ===== 본문 ===== */}
        <main className="min-w-0 flex-1 pt-2">
          <div key={current.key + role} className="page-in">
            <div className={cn("mb-7", current.key === "home" && "hidden")}>
              <div className="mb-2.5 flex items-center gap-2.5 text-[14px] text-muted-foreground">
                <i className="grid size-[34px] place-items-center rounded-full text-white not-italic" style={{ background: group.color }}>
                  <current.icon className="size-4" />
                </i>
                {group.label} · {current.sub}
              </div>
              <h2 className="font-display text-[40px] leading-[1.12] font-bold tracking-[-0.03em]">{current.label}</h2>
              <p className="mt-2 text-[16.5px] text-[#3a3a3c]">{current.desc}</p>
            </div>

            {current.key === "home" && <HomePage role={role} onNavigate={setPage} onAskAgent={() => setAgentOpen(true)} />}
            {current.key === "dashboard" && <DashboardPage role={role} onNavigate={setPage} />}
            {current.key === "systems" && <SystemsPage role={role} />}
            {current.key === "servers" && <ServersPage role={role} />}
            {current.key === "catalog" && <CatalogPage role={role} />}
            {current.key === "publish" && <PublishPage role={role} />}
            {current.key === "mcp-register" && <McpRegisterPage role={role} />}
            {current.key === "convert" && <ConvertPage role={role} />}
            {current.key === "subscriptions" && <SubscriptionsPage role={role} />}
            {current.key === "my-access" && <MyAccessPage onNavigate={setPage} />}
            {current.key === "usage-api" && <ApiUsagePage role={role} />}
            {current.key === "usage-mcp" && <McpUsagePage role={role} />}
            {current.key === "stats" && <CallStatsPage />}
            {current.key === "instances" && <InstancesPage />}
            {current.key === "docs" && <DocsPage />}
          </div>
        </main>
      </div>

      {agentOpen && (
        <AgentPanel
          onClose={() => setAgentOpen(false)}
          page={current.key}
          pageLabel={`${current.label} 화면`}
          focus={focus}
          pendingAsk={pendingAsk}
          onAsked={() => setPendingAsk(null)}
          onApply={bridge.apply}
          onNavigate={(k) => PAGES.some((p) => p.key === k) && setPage(k as PageKey)}
        />
      )}
    </div>
    </AgentBridgeContext.Provider>
  );
}
