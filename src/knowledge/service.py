"""컨설팅 문서 관리 (T2-5, admin): 업로드 → 텍스트 추출 → ChromaDB 색인, 다시 색인, 삭제, 검색 시험.

- 파일은 settings.UPLOAD_DIR/consult_docs/{문서ID}_{파일명}에 둔다(DB에는 저장소 루트 기준 상대 경로).
- 벡터 저장소의 문서 키는 'doc:{문서ID}'. 컨설팅 Agent의 근거 출처에는 문서명이 나온다.
- 추출 실패(형식 · 인코딩)는 업로드를 거절한다(아무것도 저장하지 않음). 색인 실패(임베딩 모델 등)는 문서를 '실패'로 남겨 다시 색인할 수 있게 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from src.audit.repository import AuditRepository
from src.auth.models import User
from src.knowledge.evidence import judge
from src.knowledge.extract import extract_text, ExtractError
from src.knowledge.models import ConsultDoc, DocStatus
from src.knowledge.repository import ConsultDocRepository
from src.knowledge.store import VectorStore
from src.shared.config import ROOT_DIR, settings
from src.shared.errors import Conflict, Invalid, NotFound
from src.systems.access import ensure_admin

EXCERPT = 200


def upload_dir() -> Path:
    p = Path(settings.UPLOAD_DIR)
    return (p if p.is_absolute() else ROOT_DIR / p) / "consult_docs"


def doc_key(doc: ConsultDoc) -> str:
    return f"doc:{doc.id}"


def _abs(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT_DIR / p


def _safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name.strip()
    return re.sub(r"[^\w.\- ()가-힣]", "_", name)[:150] or "document"


def _index(doc: ConsultDoc, text: str, store: VectorStore) -> None:
    try:
        doc.chunk_count = store.index_document(doc_key(doc), Path(doc.name).stem, text)  # 출처에는 확장자 없이
        doc.status, doc.error = DocStatus.INDEXED, ""
    except Exception as e:  # noqa: BLE001 - 임베딩 · 저장소 오류는 문서 상태로 남긴다
        doc.chunk_count, doc.status, doc.error = 0, DocStatus.FAILED, f"{type(e).__name__}: {e}"[:500]


def _get(db: Session, doc_id: int) -> ConsultDoc:
    doc = ConsultDocRepository(db).get(doc_id)
    if doc is None:
        raise NotFound("문서를 찾을 수 없습니다.")
    return doc


def list_docs(db: Session, user: User) -> list[ConsultDoc]:
    ensure_admin(user)
    return ConsultDocRepository(db).list(order_by=ConsultDoc.id.desc())


def upload(db: Session, user: User, filename: str, data: bytes, store: VectorStore) -> ConsultDoc:
    ensure_admin(user)
    name = _safe_name(filename)
    if not data:
        raise Invalid("파일이 비어 있습니다.", "empty_file")
    if len(data) > settings.CONSULT_DOC_MAX_BYTES:
        raise Invalid(f"파일은 {settings.CONSULT_DOC_MAX_BYTES // (1024 * 1024)}MB 이하여야 합니다.", "file_too_large")
    if ConsultDocRepository(db).list(ConsultDoc.name == name):
        raise Conflict("같은 이름의 문서가 있습니다. 기존 문서를 삭제하거나 다시 색인하세요.", "duplicate_doc")
    try:
        text = extract_text(name, data)
    except ExtractError as e:
        raise Invalid(str(e), "unsupported_doc") from e

    doc = ConsultDocRepository(db).add(ConsultDoc(name=name, uploaded_by_id=user.id, status=DocStatus.INDEXING, size_bytes=len(data)))
    path = upload_dir() / f"{doc.id}_{name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    doc.file_path = path.relative_to(ROOT_DIR).as_posix() if path.is_relative_to(ROOT_DIR) else str(path)
    _index(doc, text, store)
    AuditRepository(db).record(user.id, "consult_doc.upload", "consult_doc", doc.id, {"name": name, "chunks": doc.chunk_count, "status": doc.status.value})
    return doc


def reindex(db: Session, user: User | None, doc_id: int, store: VectorStore) -> ConsultDoc:
    if user is not None:
        ensure_admin(user)
    doc = _get(db, doc_id)
    try:
        text = extract_text(doc.file_path or doc.name, _abs(doc.file_path).read_bytes())
    except (OSError, ExtractError) as e:
        doc.chunk_count, doc.status, doc.error = 0, DocStatus.FAILED, f"파일을 읽지 못했습니다: {e}"[:500]
        return doc
    _index(doc, text, store)
    if user is not None:
        AuditRepository(db).record(user.id, "consult_doc.reindex", "consult_doc", doc.id, {"chunks": doc.chunk_count, "status": doc.status.value})
    return doc


def delete(db: Session, user: User, doc_id: int, store: VectorStore) -> None:
    ensure_admin(user)
    doc = _get(db, doc_id)
    store.delete_document(doc_key(doc))
    path = _abs(doc.file_path) if doc.file_path else None
    if path and path.is_file() and path.resolve().is_relative_to(upload_dir().resolve()):  # 업로드 폴더 밖(샘플 문서)은 지우지 않는다
        path.unlink()
    AuditRepository(db).record(user.id, "consult_doc.delete", "consult_doc", doc.id, {"name": doc.name})
    db.delete(doc)
    db.flush()


def reindex_all(db: Session, store: VectorStore) -> dict[str, int]:
    """DB에 등록된 문서를 모두 다시 색인한다(벡터 저장소를 비우고 시작 — 지워진 문서의 청크가 남지 않게)."""
    store.clear()
    docs = ConsultDocRepository(db).list(order_by=ConsultDoc.id)
    return {d.name: reindex(db, None, d.id, store).chunk_count for d in docs}


def search_test(db: Session, user: User, q: str, store: VectorStore) -> dict:
    """admin이 '이 질문에 근거가 잡히는지' 시험한다. 컨설팅 Agent와 같은 근거 판정 규칙."""
    ensure_admin(user)
    ev = judge(q, store.search(q, k=12))
    shown = ev.hits or store.search(q, k=4)
    return {
        "ok": ev.ok, "top_score": round(ev.top_score, 4), "coverage": ev.coverage, "keywords": ev.keywords, "missing": ev.missing,
        "hits": [{"doc": h.doc_name, "section": h.section, "score": round(h.score, 4), "excerpt": h.text[:EXCERPT]} for h in shown],
    }
