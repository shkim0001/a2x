"""컨설팅 문서 색인 · 검색 (ChromaDB + sentence-transformers).

- 청크: 약 500자, 100자 겹침. 마크다운 제목(#)을 절 이름으로 기록한다.
- 유사도: 코사인. score = 1 - distance (높을수록 가깝다).
- 임베딩 함수는 바꿔 끼울 수 있다(테스트는 내려받기 없는 해시 임베딩을 쓴다).
"""

from __future__ import annotations

import hashlib
import math
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.shared.config import ROOT_DIR, settings

log = logging.getLogger(__name__)

COLLECTION = "consult_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


class Embedder(Protocol):
    def __call__(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """로컬 sentence-transformers 모델(처음 쓸 때 한 번 불러온다)."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._model = None
        self._lock = threading.Lock()  # 서버 시작 시 미리 불러오기와 첫 검색이 겹쳐도 한 번만 불러온다

    def load(self) -> None:
        # sentence-transformers(torch · transformers) import가 Windows에서 20초 안팎 걸린다 → 서버 시작 때 미리 불러온다(warm_up)
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            self.load()
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class HashEmbedder:
    """테스트용: 글자 2-gram 해시로 만든 결정적 벡터(모델 내려받기 없음)."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def __call__(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            s = re.sub(r"\s+", " ", t.lower())
            for i in range(len(s) - 1):
                h = int(hashlib.md5(s[i : i + 2].encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


@dataclass
class Chunk:
    text: str
    section: str
    seq: int


@dataclass
class Hit:
    text: str
    score: float
    doc_id: str
    doc_name: str
    section: str


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """문단 단위로 모아 size 근처에서 자르고, 앞 청크의 끝 overlap 글자를 다음 청크 앞에 붙인다."""
    chunks: list[Chunk] = []
    section = ""
    buf = ""
    buf_section = ""

    def flush():
        nonlocal buf
        if buf.strip():
            chunks.append(Chunk(buf.strip(), buf_section, len(chunks)))
            buf = buf[-overlap:] if overlap else ""

    for para in re.split(r"\n\s*\n", text):
        p = para.strip()
        if not p:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", p.splitlines()[0])
        if heading:
            flush()
            buf = ""
            section = heading.group(1).strip()
        if not buf.strip():
            buf_section = section
        while len(buf) + len(p) + 1 > size and p:
            room = max(size - len(buf), 1)
            buf += ("\n" if buf else "") + p[:room]
            p = p[room:]
            flush()
            buf_section = section
        buf += ("\n" if buf else "") + p
    flush()
    return chunks


class VectorStore:
    def __init__(self, path: str | Path | None = None, embedder: Embedder | None = None, in_memory: bool = False):
        import chromadb

        self.embedder = embedder or SentenceTransformerEmbedder()
        if in_memory:
            self.client = chromadb.EphemeralClient()
        else:
            p = Path(path or settings.CHROMA_PERSIST_DIR)
            if not p.is_absolute():
                p = ROOT_DIR / p
            self.client = chromadb.PersistentClient(path=str(p))
        # 임베딩은 직접 계산해 넘긴다(ChromaDB 기본 임베딩 함수를 쓰지 않음)
        # 메모리 클라이언트는 프로세스 안에서 공유되므로 인스턴스마다 컬렉션 이름을 따로 쓴다(테스트 격리)
        name = f"{COLLECTION}_{uuid.uuid4().hex[:8]}" if in_memory else COLLECTION
        self.col = self.client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"}, embedding_function=None)

    def index_document(self, doc_id: str, doc_name: str, text: str) -> int:
        self.delete_document(doc_id)
        chunks = chunk_text(text)
        if not chunks:
            return 0
        self.col.add(
            ids=[f"{doc_id}:{c.seq}" for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=self.embedder([c.text for c in chunks]),
            metadatas=[{"doc_id": doc_id, "doc_name": doc_name, "section": c.section, "seq": c.seq} for c in chunks],
        )
        return len(chunks)

    def delete_document(self, doc_id: str) -> None:
        self.col.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return self.col.count()

    def clear(self) -> None:
        """컬렉션의 모든 청크를 지운다(전체 다시 색인용)."""
        ids = self.col.get(include=[])["ids"]
        if ids:
            self.col.delete(ids=ids)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        if self.count() == 0:
            return []
        r = self.col.query(query_embeddings=self.embedder([query]), n_results=min(k, self.count()))
        hits = []
        for text, dist, meta in zip(r["documents"][0], r["distances"][0], r["metadatas"][0]):
            hits.append(Hit(text=text, score=round(1 - float(dist), 4), doc_id=meta["doc_id"], doc_name=meta["doc_name"], section=meta.get("section", "")))
        return hits


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_store() -> VectorStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = VectorStore()
    return _store


def warm_up() -> None:
    """임베딩 모델 · 벡터 저장소를 미리 불러온다(서버 시작 시 백그라운드 스레드). 실패해도 첫 검색 때 다시 시도한다."""
    t0 = time.perf_counter()
    try:
        store = get_store()
        store.embedder(["준비"])
        log.info("RAG 준비 완료: %.1f초 (청크 %d개)", time.perf_counter() - t0, store.count())
    except Exception as e:  # noqa: BLE001 — 미리 불러오기는 선택 사항
        log.warning("RAG 미리 불러오기 실패(첫 검색 때 다시 시도): %s", e)
