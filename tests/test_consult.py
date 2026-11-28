"""T3-3 RAG 색인 · 검색과 컨설팅 Agent (해시 임베딩 · 가짜 LLM, 내려받기 · API 키 없이)."""

from types import SimpleNamespace

import anyio
import pytest

from src.agents.consult import agent as consult
from src.knowledge.index import index_samples
from src.knowledge.store import chunk_text, HashEmbedder, VectorStore
from src.tools.master_client import MasterClient
from src.tools.mock_master.server import server as master_server


@pytest.fixture(scope="module")
def store():
    s = VectorStore(in_memory=True, embedder=HashEmbedder())
    index_samples(s)
    return s


class FakeLLM:
    def __init__(self):
        self.calls = []

    @property
    def available(self):
        return True

    def complete(self, messages, system=None, **kw):
        self.calls.append({"messages": messages, "system": system})
        return SimpleNamespace(text="조회 위주라면 MCP 방식을 권장합니다 [1].", model="claude-sonnet-5-5")


@pytest.fixture(autouse=True)
def low_threshold(monkeypatch):
    """해시 임베딩은 실제 모델보다 유사도가 낮게 나오므로 기준값을 낮춘다."""
    from src.shared.config import settings

    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.1)


def test_chunking_keeps_sections_and_size():
    text = "# 제목\n\n" + "가" * 1200 + "\n\n## 둘째 절\n\n짧은 문단"
    chunks = chunk_text(text, size=500, overlap=100)
    assert all(len(c.text) <= 600 for c in chunks)
    assert chunks[0].section == "제목" and chunks[-1].section == "둘째 절"


def test_index_and_search(store):
    assert store.count() > 4
    hits = store.search("조회 위주 Agent 연계는 어떤 방식이 좋나요", k=3)
    assert hits[0].doc_name == "사내 시스템 연계 표준 가이드 v3"
    assert hits[0].section.startswith("1. 연계 방식")


def test_reindex_replaces_chunks(store):
    n = store.count()
    index_samples(store)
    assert store.count() == n


def test_answer_with_sources_uses_llm_only_with_evidence(store):
    llm = FakeLLM()
    r = anyio.run(lambda: consult.run("조회 위주 Agent 연계는 API랑 MCP 중 어떤 방식이 좋아요?", store, llm))
    assert r.used_llm == "claude-sonnet-5-5" and r.sources and r.sources[0]["no"] == 1
    sent = llm.calls[0]["messages"][0]["content"]
    assert "[근거]" in sent and "사내 시스템 연계 표준 가이드 v3" in sent  # 근거를 함께 보냈다
    assert "추측하지 말고" in llm.calls[0]["system"]


def test_no_evidence_does_not_call_llm(store, monkeypatch):
    from src.shared.config import settings

    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.99)  # 근거 없음 상황
    llm = FakeLLM()
    r = anyio.run(lambda: consult.run("화성 탐사선 API 연계 표준이 뭐야", store, llm, master=MasterClient(master_server)))
    assert llm.calls == [] and r.sources == []
    assert "근거를 찾지 못했습니다" in r.answer and "#a2x-help" in r.answer


def test_without_llm_shows_excerpts(store):
    r = anyio.run(lambda: consult.run("방화벽 신청할 때 필요한 정보", store, SimpleNamespace(available=False)))
    assert r.used_llm is None and "방화벽 신청 절차" in r.answer
