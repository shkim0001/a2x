"""컨설팅 Agent (T3-3): 사내 문서 근거 기반 연계 방식 제안.

근거 판정은 코드(src/knowledge/evidence.py: 하이브리드 재정렬 + 유사도 · 핵심어 포함률). 근거가 없으면 LLM을 부르지 않고
'문서에서 찾지 못함 + 담당자 문의'로 답한다(가드레일 3). 근거가 있으면 LLM이 근거 발췌만으로 답한다."""

from __future__ import annotations

import re

from anyio import to_thread

from src.agents.consult.prompts import SYSTEM
from src.agents.state import AgentResult
from src.knowledge.evidence import judge
from src.knowledge.store import Hit, VectorStore
from src.shared import trace
from src.shared.llm import LLMClient, LLMUnavailable, note_skipped
from src.tools.master_client import MasterClient, MasterError


EXCERPT = 180
GUIDE_DOC = "A2X 포탈 사용 가이드"
# 가이드 질문 → 열어 줄 화면(앞에서부터 첫 일치)
GUIDE_PAGES = [
    (r"(api|mcp).*수정|수정.*(api|mcp)", "catalog", "카탈로그 열기"),
    (r"서버", "servers", "서버 화면 열기"),
    (r"담당자", "systems", "시스템 화면 열기"),
    (r"시스템\s?(등록|정보|추가)|시스템을", "systems", "시스템 화면 열기"),
    (r"변환", "convert", "MCP 변환 화면 열기"),
    (r"mcp\s?(서버)?\s?등록", "mcp-register", "MCP 등록 화면 열기"),
    (r"api\s?등록", "publish", "API 등록 화면 열기"),
    (r"tool|툴", "catalog", "카탈로그에서 Tool 신청"),
    (r"구독|사용\s?신청", "catalog", "카탈로그 열기"),
    (r"승인|반려|해지", "subscriptions", "구독 · 승인 화면 열기"),
    (r"사용내역|모니터링|통계|호출\s?로그", "usage-api", "사용내역 열기"),
    (r"문서|색인", "docs", "컨설팅 문서 열기"),
]


def _guide_actions(question: str, hits: list[Hit]) -> list[dict[str, str]]:
    if not any(h.doc_name == GUIDE_DOC for h in hits):
        return []
    t = question.lower()
    page = next(((pg, label) for pat, pg, label in GUIDE_PAGES if re.search(pat, t)), None)
    return [{"type": "open", "page": page[0], "label": page[1]}] if page else []


POOL = 12  # 재정렬용으로 넓게 뽑는 청크 수


def _fmt_sources(hits: list[Hit]) -> list[dict]:
    return [{"no": i, "doc": h.doc_name, "section": h.section, "score": h.score, "excerpt": h.text[:EXCERPT]} for i, h in enumerate(hits, 1)]


async def _contact(master: MasterClient | None) -> str:
    try:
        c = await (master or MasterClient()).call("get_contact", dept="A2X 플랫폼팀")
        return f"{c['dept']}({c['channel']}, {c['email']})"
    except (MasterError, KeyError, TypeError):
        return "A2X 플랫폼팀(#a2x-help)"


async def run(question: str, store: VectorStore, llm: LLMClient, master: MasterClient | None = None, k: int = 4) -> AgentResult:
    # 임베딩 검색 · LLM 호출은 동기 작업이라 스레드에서 실행한다(서버 이벤트 루프를 막지 않음)
    with trace.span("rag", f"문서 청크 검색 (k={POOL})") as s:
        hits = await to_thread.run_sync(lambda: store.search(question, k=POOL))
        s.detail = f"{len(hits)}건 · 최고 유사도 {hits[0].score:.2f}" if hits else "결과 없음"
    ev = judge(question, hits, k=k)
    missing = f" · 문서에 없는 말: {', '.join(ev.missing)}" if ev.missing else ""
    trace.step(trace.actor(), "근거 판정(코드)", f"{'근거 있음' if ev.ok else '근거 없음'} · 핵심어 포함률 {ev.coverage:.0%}{missing}", ok=ev.ok)

    if not ev.ok:
        trace.step(trace.actor(), "LLM 호출 안 함", "근거가 없으면 추측하지 않는다(가드레일 3)")
        contact = await _contact(master)
        return AgentResult(
            answer=f"사내 컨설팅 문서에서 이 질문의 근거를 찾지 못했습니다. 추측으로 답하지 않겠습니다. {contact}에 문의해 주세요.",
            used_tools=["rag.search", "master.get_contact"],
        )

    top = ev.hits
    sources = _fmt_sources(top)
    if llm.available:
        evidence = "\n\n".join(f"[{s['no']}] ({s['doc']} › {s['section']})\n{h.text}" for s, h in zip(sources, top))
        try:
            content = f"[근거]\n{evidence}\n\n[질문]\n{question}"
            r = await to_thread.run_sync(lambda: llm.complete([{"role": "user", "content": content}], system=SYSTEM, max_tokens=1500, effort="low"))
            return AgentResult(answer=r.text.strip(), sources=sources, actions=_guide_actions(question, top), used_tools=["rag.search"], used_llm=r.model)
        except LLMUnavailable:
            pass

    # LLM 없이: 근거 발췌를 그대로 보여준다(포탈 가이드가 1순위면 그 절 전체)
    if not llm.available:
        note_skipped()
    actions = _guide_actions(question, top)
    if top[0].doc_name == GUIDE_DOC:
        body = top[0].text.split("\n", 1)[-1].strip() if top[0].text.startswith("#") else top[0].text.strip()
        return AgentResult(answer=f"포탈 사용 가이드 › {top[0].section}\n{body}", sources=sources, actions=actions, used_tools=["rag.search"])
    lines = [f"• {s['doc']} › {s['section']}: {h.text[:EXCERPT].replace(chr(10), ' ')}…" for s, h in zip(sources[:2], top[:2])]
    return AgentResult(answer="사내 문서에서 찾은 관련 내용입니다.\n" + "\n".join(lines), sources=sources, actions=actions, used_tools=["rag.search"])
