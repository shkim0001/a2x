"""컨설팅 문서 관리 API (admin). 파일은 multipart 대신 원본 바이트(요청 본문)로 받는다(python-multipart 미승인, 레이아웃 엑셀과 같은 방식)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.auth.deps import current_user
from src.auth.models import User
from src.auth.repository import UserRepository
from src.knowledge import service as svc
from src.knowledge.models import ConsultDoc
from src.knowledge.schemas import DocOut, SearchHit, SearchOut
from src.knowledge.store import get_store, VectorStore
from src.shared.db.session import get_db

router = APIRouter(prefix="/consult-docs", tags=["consult-docs"])


def get_doc_store() -> VectorStore:
    return get_store()


def _out(db: Session, d: ConsultDoc) -> dict:
    u = UserRepository(db).get(d.uploaded_by_id) if d.uploaded_by_id else None
    return {
        "id": d.id, "name": d.name, "status": d.status.value, "chunk_count": d.chunk_count, "size_bytes": d.size_bytes, "error": d.error,
        "uploaded_by": u.name if u else None, "created_at": d.created_at, "is_sample": "knowledge/sample_docs/" in (d.file_path or ""),
    }


@router.get("", response_model=list[DocOut])
def list_docs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_out(db, d) for d in svc.list_docs(db, user)]


@router.post("", response_model=DocOut, status_code=201)
async def upload(request: Request, filename: str = Query(min_length=1, max_length=200), user: User = Depends(current_user),
                 db: Session = Depends(get_db), store: VectorStore = Depends(get_doc_store)):
    data = await request.body()
    # 추출 · 임베딩은 오래 걸리는 동기 작업이라 스레드에서 실행한다(그동안 다른 요청을 막지 않음)
    doc = await run_in_threadpool(svc.upload, db, user, filename, data, store)
    db.commit()
    return _out(db, doc)


@router.post("/{doc_id}/reindex", response_model=DocOut)
def reindex(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), store: VectorStore = Depends(get_doc_store)):
    doc = svc.reindex(db, user, doc_id, store)
    db.commit()
    return _out(db, doc)


@router.delete("/{doc_id}", status_code=204)
def delete(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), store: VectorStore = Depends(get_doc_store)):
    svc.delete(db, user, doc_id, store)
    db.commit()


@router.get("/search", response_model=SearchOut)
def search(q: str = Query(min_length=1, max_length=300), user: User = Depends(current_user), db: Session = Depends(get_db),
           store: VectorStore = Depends(get_doc_store)):
    return svc.search_test(db, user, q, store)
