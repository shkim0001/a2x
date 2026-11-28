"""A2X Agent 채팅 API (AGENTS.md 7절). 대화 기록은 서버에 저장하지 않고, 화면이 최근 턴을 history로 보낸다."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents import service as svc
from src.agents.schemas import ChatContext, ChatIn, ChatOut, Turn
from src.auth.deps import current_user
from src.auth.models import User
from src.shared.db.session import get_db

router = APIRouter(prefix="/agent", tags=["agent"])


def get_runtime() -> svc.AgentRuntime:
    return svc.default_runtime()


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db), runtime: svc.AgentRuntime = Depends(get_runtime)):
    out = await svc.run_chat(
        db, user, runtime, body.message.strip(), page=body.context.page, asset_id=body.context.asset_id,
        transaction_id=body.context.transaction_id, history=[t.model_dump() for t in body.history],
    )
    db.commit()  # 감사 로그
    return out
