"""A2X Agent 그래프 (LangGraph): pre_guard → supervisor(규칙 라우팅) → 업무 Agent 하나 → post_guard.

의존성(포탈 Tool · LLM · 벡터 저장소 · 마스터 MCP)은 요청마다 config["configurable"]["deps"]로 넘긴다.
그래프는 한 번만 컴파일한다. 대화 기록은 서버에 저장하지 않는다(체크포인터 없음).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from src.agents import guard, supervisor
from src.agents.automation import agent as automation
from src.agents.consult import agent as consult
from src.agents.devsupport import agent as devsupport
from src.agents.error_action import agent as error_action
from src.agents.state import AgentResult, AgentState, UserCtx
from src.knowledge.store import VectorStore
from src.shared import trace
from src.shared.llm import LLMClient
from src.tools.master_client import MasterClient
from src.tools.portal import PortalTools


@dataclass
class Deps:
    portal: PortalTools
    user: UserCtx
    llm: LLMClient
    store: Callable[[], VectorStore]  # 임베딩 모델을 읽는 데 시간이 걸려 컨설팅일 때만 연다
    master: MasterClient
    irp: MasterClient | None = None  # IRP(시스템 마스터) MCP
    dcm: MasterClient | None = None  # DCM(서버 자산) MCP
    now: datetime | None = None  # 테스트용 고정 시각


def _external(d: "Deps", code: str) -> MasterClient:
    """외부 시스템 MCP 클라이언트: 기본은 A2X 중계(A2X Agent 구독 + 사용자 Tool 권한 + 호출 로그)."""
    from src.shared.config import settings

    if settings.AGENT_VIA_A2X:
        return d.portal.relay_mcp(code, code)
    return MasterClient.irp() if code == "IRP" else MasterClient.dcm()


def _deps(config: RunnableConfig) -> Deps:
    return config["configurable"]["deps"]


def pre_guard(state: AgentState) -> dict[str, Any]:
    preview, _ = guard.mask_text(state["message"][:40])
    ctx = " · ".join(f"{k}={state[k]}" for k in ("page", "asset_id", "transaction_id") if state.get(k))
    trace.step("guard", "질문", f"\"{preview}{'…' if len(state['message']) > 40 else ''}\"" + (f" ({ctx})" if ctx else ""), src="user")
    check = guard.check_request(state["message"])
    out: dict[str, Any] = {"check": check, "guard_notes": list(check.notes)}
    if check.blocked:
        out.update(route="guard", rule="guard:" + check.notes[0].split(":", 1)[1], result=check.blocked)
        reason = {"secret": "비밀 값 요구", "write": "변경 요청(Agent는 쓰기 없음)"}.get(out["rule"].split(":")[1], out["rule"])
        trace.step("guard", "요청 차단", reason, ok=False, src="guard")
    elif check.wants_submit:
        trace.step("guard", "요청 검사", "제출 요청 표시(채움만 하고 제출 안내)", src="guard")
    return out


def route_node(state: AgentState) -> dict[str, Any]:
    trace.step("supervisor", "검사 통과 → 라우팅", src="guard")
    d = supervisor.route(state["message"], page=state.get("page"), transaction_id=state.get("transaction_id"))
    trace.step(f"agent:{d.route}", f"{d.label} Agent에 위임", f"규칙 {d.rule}", src="supervisor")
    return {"route": d.route, "rule": d.rule, "message": d.message or state["message"]}


async def consult_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    with trace.acting("agent:consult"):  # 이 Agent가 부르는 Tool · RAG · LLM 호출의 출발점
        return {"result": await consult.run(state["message"], d.store(), d.llm, master=d.master)}


async def automation_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    with trace.acting("agent:automation"):  # 이 Agent가 부르는 Tool · RAG · LLM 호출의 출발점
        return {"result": await automation.run(state["message"], d.portal, d.master, page=state.get("page"), asset_id=state.get("asset_id"),
                                               irp=d.irp or _external(d, "IRP"), dcm=d.dcm or _external(d, "DCM"))}


async def devsupport_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    with trace.acting("agent:devsupport"):  # 이 Agent가 부르는 Tool · RAG · LLM 호출의 출발점
        return {"result": await devsupport.run(state["message"], d.portal, d.user, llm=d.llm, asset_id=state.get("asset_id"))}


async def error_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    with trace.acting("agent:error"):  # 이 Agent가 부르는 Tool · RAG · LLM 호출의 출발점
        return {"result": await error_action.run(state["message"], d.portal, llm=d.llm, transaction_id=state.get("transaction_id"), page=state.get("page"), now=d.now)}


def post_guard(state: AgentState) -> dict[str, Any]:
    result: AgentResult = state.get("result") or AgentResult(answer="요청을 처리하지 못했습니다. 다시 시도해 주세요.")
    route = state.get("route", "guard")
    if route != "guard":
        made = ["양식 제안" if result.form_suggestion else "", f"출처 {len(result.sources)}건" if result.sources else "", f"선택지 {len(result.actions)}개" if result.actions else ""]
        trace.step("guard", "응답 검사 요청", " · ".join(m for m in made if m) or "답변", src=f"agent:{route}")
    result, notes = guard.sanitize(result, state.get("check"))
    masked = next((n.split(":")[1] for n in notes if n.startswith("masked:")), None)
    checks = [f"민감정보 {masked}건 가림" if masked else "민감정보 없음"] + (["'제출은 직접' 안내 추가"] if "no_submit" in notes else [])
    trace.step("user", "응답", " · ".join(checks), src="guard")
    return {"result": result, "guard_notes": [*state.get("guard_notes", []), *notes]}


AGENT_NODES = {"consult": consult_node, "automation": automation_node, "devsupport": devsupport_node, "error": error_node}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("pre_guard", pre_guard)
    g.add_node("supervisor", route_node)
    for name, fn in AGENT_NODES.items():
        g.add_node(name, fn)
        g.add_edge(name, "post_guard")
    g.add_node("post_guard", post_guard)
    g.add_edge(START, "pre_guard")
    g.add_conditional_edges("pre_guard", lambda s: "post_guard" if s.get("result") else "supervisor", ["post_guard", "supervisor"])
    g.add_conditional_edges("supervisor", lambda s: s["route"], list(AGENT_NODES))
    g.add_edge("post_guard", END)
    return g.compile()


GRAPH = build_graph()


async def chat(deps: Deps, message: str, page: str | None = None, asset_id: int | None = None, transaction_id: str | None = None,
               history: list[dict[str, str]] | None = None) -> AgentState:
    state: AgentState = {"message": message, "page": page, "asset_id": asset_id, "transaction_id": transaction_id, "history": history or [], "user": deps.user}
    with trace.collecting() as steps:
        out = await GRAPH.ainvoke(state, config={"configurable": {"deps": deps}})
    return {**out, "trace": steps}
