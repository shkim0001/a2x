"""사용자 검색 API(담당자 지정 화면용). 응답은 이름 · 이메일만."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth import service
from src.auth.deps import current_user
from src.auth.models import User
from src.auth.schemas import UserBrief
from src.shared.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserBrief])
def search_users(q: str | None = Query(default=None, max_length=100), limit: int = Query(default=20, ge=1, le=50),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.search_users(db, user, q, limit)
