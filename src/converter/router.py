"""API → MCP 변환 API (T2-6)."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.deps import current_user
from src.auth.models import User
from src.catalog.router import _detail
from src.catalog.schemas import AssetDetail
from src.converter import service as svc
from src.converter.schemas import ConvertIn, ConvertToolIn, ToolSuggestion
from src.shared.db.session import get_db

router = APIRouter(tags=["convert"])


@router.get("/assets/{api_id}/convert/preview", response_model=list[ToolSuggestion])
def preview(api_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """오퍼레이션별 Tool 이름 · 설명 · 조회/변경 · 입력 스키마(규칙 기반) 제안."""
    return svc.preview(db, user, api_id)


@router.post("/assets/{api_id}/convert", response_model=AssetDetail, status_code=201)
def convert(api_id: int, body: ConvertIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mcp = svc.convert(db, user, api_id, body.name, body.description, [t.model_dump() for t in body.tools], body.submit)
    db.commit()
    return _detail(db, mcp)
