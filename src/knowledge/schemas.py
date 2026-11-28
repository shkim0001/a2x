"""지식(컨설팅 문서) 도메인 입출력 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocOut(BaseModel):
    id: int
    name: str
    status: str
    chunk_count: int
    size_bytes: int
    error: str
    uploaded_by: str | None
    created_at: datetime
    is_sample: bool  # 저장소에 들어 있는 샘플 문서(삭제해도 원본 파일은 남음)


class SearchHit(BaseModel):
    doc: str
    section: str
    score: float
    excerpt: str


class SearchOut(BaseModel):
    ok: bool
    top_score: float
    coverage: float
    keywords: list[str]
    missing: list[str]
    hits: list[SearchHit]
