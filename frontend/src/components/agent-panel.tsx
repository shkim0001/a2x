import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUpRight, Bot, Check, Copy, FileText, GitBranch, Loader2, Send, ShieldAlert, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { agentChat, type AgentRoute, type ChatResponse, type ChatTurn, type FormSuggestion } from "@/lib/api";
import { useAgentBridge, type AgentFocus } from "@/lib/agent-bridge";
import { AgentFlow } from "@/components/agent-flow";
import { cn } from "@/lib/utils";

const ROUTE_LABEL: Record<AgentRoute, string> = {
  consult: "컨설팅",
  automation: "프로세스 자동화",
  devsupport: "개발 지원",
  error: "오류 조치",
  guard: "가드레일",
};
const FORM_LABEL = { api: "API 등록", mcp: "MCP 등록", subscription: "시스템 구독 신청", system: "시스템 등록", server: "서버 등록", system_servers: "시스템 등록 · 서버 정보" } as const;
const HISTORY_TURNS = 6;
const EXAMPLES = ["조회 위주 Agent 연계는 어떤 방식이 좋아요?", "재고 이력 API 등록 채워줘", "고객 정보 MCP 호출 python 코드 예시", "어제 오류 원인 정리해줘"];

type Msg = { role: "user"; text: string } | { role: "agent"; text: string; res?: ChatResponse; error?: boolean };

// ---------- 답변 표시: 굵게 · 목록 · 코드 블록만 (마크다운 라이브러리 없이) ----------

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => (part.startsWith("**") && part.endsWith("**") ? <b key={i}>{part.slice(2, -2)}</b> : part));
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="relative my-1.5 overflow-hidden rounded-xl bg-[#1d1d1f]">
      <div className="flex items-center justify-between px-3 pt-1.5 text-[11px] text-white/50">
        <span>{lang || "code"}</span>
        <button onClick={copy} className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-white/10 hover:text-white">
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? "복사됨" : "복사"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 pt-1 pb-2.5 font-mono text-[11.5px] leading-[1.5] text-[#f5f5f7]">{code}</pre>
    </div>
  );
}

function Answer({ text }: { text: string }) {
  const parts = text.split("```");
  return (
    <div className="space-y-1.5">
      {parts.map((seg, i) => {
        if (i % 2 === 1) {
          const nl = seg.indexOf("\n");
          return <CodeBlock key={i} lang={nl > 0 ? seg.slice(0, nl).trim() : ""} code={(nl >= 0 ? seg.slice(nl + 1) : seg).replace(/\n$/, "")} />;
        }
        return seg
          .split("\n")
          .filter((l, j, arr) => l.trim() || (j > 0 && j < arr.length - 1 && arr[j - 1].trim()))
          .map((line, j) => {
            const nested = /^\s{2,}-\s/.test(line);
            const bullet = /^\s*-\s/.test(line);
            const num = /^\d+\.\s/.test(line);
            if (!line.trim()) return <div key={`${i}-${j}`} className="h-1" />;
            return (
              <p key={`${i}-${j}`} className={cn("leading-[1.55]", bullet && "relative pl-3.5", nested && "ml-3.5 text-[13px] text-[#3a3a3c]", num && "pl-1")}>
                {bullet && <span className="absolute left-0.5 text-muted-foreground">•</span>}
                {inline(bullet ? line.replace(/^\s*-\s/, "") : line)}
              </p>
            );
          });
      })}
    </div>
  );
}

function SuggestionCard({ s, onApply }: { s: FormSuggestion; onApply: () => void }) {
  const [done, setDone] = useState(false);
  return (
    <div className="mt-2 rounded-2xl bg-white p-3 ring-1 ring-[#2f6bff]/25">
      <p className="flex items-center gap-1.5 text-[13px] font-bold text-[#2f6bff]">
        <Sparkles className="size-3.5" /> {FORM_LABEL[s.form]} 양식 제안
      </p>
      {s.source?.label && <p className="mt-0.5 text-[12px] text-muted-foreground">출처: {s.source.label}</p>}
      <Button
        size="sm"
        className="mt-2 w-full"
        disabled={done}
        onClick={() => {
          onApply();
          setDone(true);
        }}
      >
        {done ? <><Check /> 양식에 채웠습니다 — 확인 후 직접 제출</> : "양식에 채우기"}
      </Button>
    </div>
  );
}

export function AgentPanel({
  onClose,
  page,
  pageLabel,
  focus,
  pendingAsk,
  onAsked,
  onApply,
  onNavigate,
}: {
  onClose: () => void;
  page: string;
  pageLabel: string;
  focus: AgentFocus;
  pendingAsk: { id: number; text: string } | null;
  onAsked: () => void;
  onApply: (s: FormSuggestion) => void;
  onNavigate: (page: string) => void;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "agent", text: "무엇을 도와드릴까요? 연계 방식 상담, 등록 · 구독 양식 채움, 연계 코드 예시, 오류 원인 분석을 할 수 있습니다." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bridge = useAgentBridge(); // 'Tool 사용 신청' 행동: 그 MCP 서버를 담은 카탈로그 사용 신청 화면
  const bottom = useRef<HTMLDivElement>(null);
  // 실행 흐름 패널: 켜 두면 가장 최근 답변을 따라가고, 답변의 '흐름 보기'로 특정 답변을 고를 수 있다
  const [flowOn, setFlowOn] = useState(true);
  const [flowFor, setFlowFor] = useState<number | null>(null);
  const flowIdx = flowFor ?? msgs.reduce((last, m, i) => (m.role === "agent" && m.res ? i : last), -1);
  const flowMsg = flowIdx >= 0 ? msgs[flowIdx] : undefined;
  const flowRes = flowMsg && flowMsg.role === "agent" ? flowMsg.res : undefined;
  const flowQuestion = flowIdx > 0 && msgs[flowIdx - 1].role === "user" ? msgs[flowIdx - 1].text : undefined;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" }); // 반환값(Promise일 수 있음)을 정리 함수로 넘기지 않는다
  }, [msgs, busy]);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    // 서버는 대화 기록을 저장하지 않으므로 최근 턴을 함께 보낸다
    const history: ChatTurn[] = msgs
      .slice(1)
      .slice(-HISTORY_TURNS)
      .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.text.slice(0, 2000) }));
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    try {
      const res = await agentChat(text, { page, ...focus }, history);
      setMsgs((m) => [...m, { role: "agent", text: res.answer, res }]);
      setFlowFor(null); // 새 답변의 흐름을 따라간다
    } catch (e) {
      setMsgs((m) => [...m, { role: "agent", text: `요청을 처리하지 못했습니다: ${(e as Error).message}`, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  // 화면에서 보낸 질문(예: 양식의 'Agent로 채우기'). 개발 모드(StrictMode)에서 효과가 두 번 실행돼도 한 번만 보낸다
  const handled = useRef<number | null>(null);
  useEffect(() => {
    if (pendingAsk && handled.current !== pendingAsk.id) {
      handled.current = pendingAsk.id;
      onAsked();
      void send(pendingAsk.text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAsk]);

  const context = [pageLabel, focus.asset_id ? `선택한 자산 #${focus.asset_id}` : null, focus.transaction_id ? `트랜잭션 ${focus.transaction_id}` : null].filter(Boolean).join(" · ");

  return (
    <>
    {flowOn && flowRes && flowRes.trace?.length > 0 && (
      <AgentFlow key={flowIdx} steps={flowRes.trace} route={flowRes.route} question={flowQuestion} onClose={() => setFlowOn(false)} />
    )}
    <aside className="page-in fixed top-[100px] right-5 bottom-5 z-40 flex w-[390px] flex-col overflow-hidden rounded-[22px] bg-white/85 shadow-[0_24px_70px_rgb(0_0_0/0.14),0_0_0_1px_rgb(0_0_0/0.05)] backdrop-blur-xl">
      <div className="flex h-16 shrink-0 items-center justify-between bg-gradient-to-r from-[#2f6bff] via-[#7d5cf5] to-[#bf5af2] px-5 text-white">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-full bg-white/20"><Bot className="size-4.5" /></span>
          <div>
            <b className="block font-display font-bold tracking-[-0.025em] text-[19px] leading-tight">A2X Agent</b>
            <small className="text-[11px] text-white/80">컨설팅 · 신청 대행 · 개발 지원 · 오류 조치</small>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setFlowOn((v) => !v)}
            className={cn("flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-bold", flowOn ? "bg-white text-[#5e3ce6]" : "text-white hover:bg-white/20")}
            title="Agent 실행 흐름(모듈 간 호출) 보기"
          >
            <GitBranch className="size-3.5" /> 흐름
          </button>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="닫기" className="text-white hover:bg-white/20 hover:text-white">
            <X />
          </Button>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-[18px] rounded-br-md bg-primary px-3.5 py-2.5 text-[14.5px] whitespace-pre-wrap text-primary-foreground">{m.text}</div>
            </div>
          ) : (
            <div key={i} className="flex flex-col items-start gap-1">
              {m.res && (
                <Badge variant={m.res.route === "guard" ? "warning" : "violet"} title={`규칙: ${m.res.rule}`}>
                  {m.res.route === "guard" ? <ShieldAlert className="mr-1 size-3" /> : "→ "}
                  {ROUTE_LABEL[m.res.route]}
                  {m.res.route !== "guard" && " Agent"}
                </Badge>
              )}
              <div className={cn("w-full max-w-[94%] rounded-[18px] rounded-bl-md px-3.5 py-2.5 text-[14px]", m.error ? "bg-[#fdecee] text-[#d70015]" : "bg-[#f0f0f2]")}>
                <Answer text={m.text} />
                {m.res?.form_suggestion && <SuggestionCard s={m.res.form_suggestion} onApply={() => onApply(m.res!.form_suggestion!)} />}
                {!!m.res?.sources.filter((s) => s.doc).length && (
                  <div className="mt-2 space-y-0.5 border-t border-black/[0.06] pt-2">
                    {m.res.sources.filter((s) => s.doc).map((s) => (
                      <p key={`${s.no}-${s.doc}-${s.section}`} className="flex items-start gap-1 text-[11.5px] text-muted-foreground" title={s.excerpt}>
                        <FileText className="mt-0.5 size-3 shrink-0" />[{s.no}] {s.doc} › {s.section}
                      </p>
                    ))}
                  </div>
                )}
              </div>
              {!!m.res?.actions.length && (
                <div className="flex max-w-[94%] flex-wrap gap-1.5">
                  {m.res.actions.map((a, j) =>
                    a.type === "ask" ? (
                      <button key={j} onClick={() => send(a.message ?? a.label)} disabled={busy} className="rounded-full bg-white px-3 py-1 text-[12.5px] ring-1 ring-black/10 hover:bg-accent disabled:opacity-50">
                        {a.label}
                      </button>
                    ) : (
                      <button
                        key={j}
                        onClick={() => (a.type === "request" && a.asset_id ? bridge.request([Number(a.asset_id)]) : a.page && onNavigate(a.page))}
                        className="flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-[12.5px] font-bold text-[#0058b9] hover:bg-[#dcebfb]"
                      >
                        {a.label} <ArrowUpRight className="size-3" />
                      </button>
                    ),
                  )}
                </div>
              )}
              {m.res && (
                <span className="flex items-center gap-2 px-1 text-[10.5px] text-muted-foreground">
                  {m.res.used_llm ? `답변: ${m.res.used_llm}` : "규칙 기반 응답"}
                  {m.res.trace?.length > 0 && (
                    <button
                      onClick={() => {
                        setFlowFor(i);
                        setFlowOn(true);
                      }}
                      className={cn("flex items-center gap-0.5 font-bold hover:text-primary", flowOn && flowIdx === i ? "text-primary" : "")}
                    >
                      <GitBranch className="size-3" /> 흐름 보기 ({m.res.trace.length}단계)
                    </button>
                  )}
                </span>
              )}
            </div>
          ),
        )}
        {msgs.length === 1 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {EXAMPLES.map((q) => (
              <button key={q} onClick={() => send(q)} className="rounded-full bg-white px-3 py-1 text-[12.5px] text-[#3a3a3c] ring-1 ring-black/10 hover:bg-accent">
                {q}
              </button>
            ))}
          </div>
        )}
        {busy && (
          <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> 답변을 만드는 중…
          </div>
        )}
        <div ref={bottom} />
      </div>

      <div className="shrink-0 border-t border-black/[0.06] p-3">
        <p className="mb-2 truncate text-[11px] text-muted-foreground">문맥: {context}</p>
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && send(input)}
            placeholder="예: 어제 오류 원인 알려줘"
            disabled={busy}
          />
          <Button size="icon" onClick={() => send(input)} disabled={busy || !input.trim()} aria-label="보내기">
            <Send />
          </Button>
        </div>
        <p className="mt-2 text-[10.5px] text-muted-foreground">Agent는 등록 · 신청을 제출하지 않습니다. 채운 값은 화면에서 확인 후 직접 제출하세요.</p>
      </div>
    </aside>
    </>
  );
}
