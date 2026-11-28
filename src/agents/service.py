"""A2X Agent 채팅 서비스: 로그인 사용자로 그래프를 실행하고 감사 로그를 남긴다.

감사 로그에는 질문 요약(가린 앞부분) · 라우팅 결과 · 사용 Tool · 답한 모델 · 가드레일 표시만 남기고 답변 원문은 남기지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from src.agents import guard
from src.agents.graph import chat, Deps
from src.agents.state import UserCtx
from src.audit.repository import AuditRepository
from src.auth.models import User
from src.knowledge.store import get_store, VectorStore
from src.shared.llm import get_llm, LLMClient
from src.systems.access import effective_role
from src.systems.repository import SystemRepository
from src.tools.master_client import MasterClient
from src.tools.portal import PortalTools

SUMMARY_LEN = 60


@dataclass
class AgentRuntime:
    """요청과 무관한 공용 의존성(테스트에서 바꿔 끼운다)."""

    llm: LLMClient
    store: Callable[[], VectorStore]
    master: MasterClient
    irp: MasterClient | None = None  # 비우면 설정의 IRP_MCP_URL
    dcm: MasterClient | None = None  # 비우면 설정의 DCM_MCP_URL


def default_runtime() -> AgentRuntime:
    return AgentRuntime(llm=get_llm(), store=get_store, master=MasterClient())


def user_ctx(db: Session, user: User) -> UserCtx:
    return UserCtx(id=user.id, name=user.name, email=user.email, role=effective_role(db, user), managed_system_ids=sorted(SystemRepository(db).managed_ids(user.id)))


async def run_chat(db: Session, user: User, runtime: AgentRuntime, message: str, page: str | None = None, asset_id: int | None = None,
                   transaction_id: str | None = None, history: list[dict[str, str]] | None = None) -> dict:
    deps = Deps(portal=PortalTools(db, user), user=user_ctx(db, user), llm=runtime.llm, store=runtime.store, master=runtime.master,
                irp=runtime.irp, dcm=runtime.dcm)
    state = await chat(deps, message, page=page, asset_id=asset_id, transaction_id=transaction_id, history=history)
    r = state["result"]
    summary, _ = guard.mask_text(message[:SUMMARY_LEN])
    AuditRepository(db).record(user.id, "agent.chat", "agent", state["route"], {
        "question": summary + ("…" if len(message) > SUMMARY_LEN else ""), "page": page, "route": state["route"], "rule": state["rule"],
        "tools": r.used_tools, "llm": r.used_llm, "guard": state.get("guard_notes", []),
    })
    return {
        "route": state["route"], "rule": state["rule"], "answer": r.answer, "sources": r.sources, "form_suggestion": r.form_suggestion,
        "actions": r.actions, "used_llm": r.used_llm, "guard_notes": state.get("guard_notes", []), "trace": state.get("trace", []),
    }
