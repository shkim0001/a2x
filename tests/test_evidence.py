"""T3-3 근거 판정 규칙(src/knowledge/evidence.py).

단위 테스트는 가짜 Hit로 규칙만 본다. 실제 임베딩 모델 보정 테스트는 모델을 읽어야 하므로
A2X_REAL_EMBEDDING=1 일 때만 돈다(색인: python -m src.knowledge.index).
"""

import os

import pytest

from src.knowledge.evidence import judge, keywords
from src.knowledge.store import Hit


def hit(text, score, section="절"):
    return Hit(text=text, score=score, doc_id="d", doc_name="문서", section=section)


def test_keywords_strip_particles_endings_and_stopwords():
    assert keywords("429가 반복되면 어떻게 하나요") == ["반복"]
    assert keywords("API를 MCP로 변환할 때 장단점이 뭐야") == ["변환", "장단점"]
    assert keywords("방화벽 신청 절차가 궁금해요") == ["방화벽", "신청", "절차"]
    assert keywords("오늘 점심 메뉴 추천해줘") == ["오늘", "점심", "메뉴"]


def test_generic_words_alone_are_not_evidence():
    # 유사도는 기준 이상이지만 핵심어(화성 · 탐사선)가 문서에 없다
    ev = judge("화성 탐사선 API 연계 표준이 뭐야", [hit("API 연계 표준은 조회 위주면 MCP를 쓴다", 0.41)])
    assert not ev.ok and ev.missing == ["화성", "탐사선"] and ev.hits == []


def test_keyword_match_rescues_low_similarity_and_reranks():
    hits = [
        hit("방화벽 신청은 포탈에서 한다", 0.23),
        hit("저장, 승인, 스테이지, 운영 순서로 진행한다. 운영 상태가 된 API만 구독", 0.10, section="5. 등록 절차"),
    ]
    ev = judge("운영 상태가 되려면 어떤 절차를 거치나요", hits)
    assert ev.ok and ev.hits[0].section == "5. 등록 절차"  # 핵심어가 많은 청크가 1위로


def test_strong_similarity_passes_without_full_coverage():
    ev = judge("API를 MCP로 변환할 때 장단점이 뭐야", [hit("API → MCP 변환을 먼저 검토한다", 0.82)])
    assert ev.ok and ev.coverage == 0.5


def test_no_hits():
    ev = judge("아무 질문", [])
    assert not ev.ok and ev.top_score == 0.0


# 실측 보정 세트: (근거 있어야 함, 질문)
CALIBRATION = [
    (True, "조회 위주 Agent 연계는 API랑 MCP 중 어떤 방식이 좋아요?"),
    (True, "API를 MCP로 변환할 때 장단점이 뭐야"),
    (True, "외부 SaaS 연동 보안 가이드 알려줘"),
    (True, "방화벽 신청 절차가 궁금해요"),
    (True, "개인정보가 있는 API는 어떻게 열어야 하나요"),
    (True, "MCP 서버 인증은 어떻게 해야 하나요"),
    (True, "429가 반복되면 어떻게 하나요"),
    (True, "시스템 구독 해지하면 Tool 권한은 어떻게 되나요"),
    (True, "Tool 이름은 어떻게 짓나요"),
    (True, "운영 상태가 되려면 어떤 절차를 거치나요"),
    (False, "화성 탐사선 API 연계 표준이 뭐야"),
    (False, "오늘 점심 메뉴 추천해줘"),
    (False, "주식 투자 방법 알려줘"),
    (False, "회사 휴가 규정이 어떻게 되나요"),
    (False, "블록체인 노드 연동 표준"),
]


@pytest.mark.skipif(os.environ.get("A2X_REAL_EMBEDDING") != "1", reason="실제 임베딩 모델 보정(A2X_REAL_EMBEDDING=1)")
def test_calibration_with_real_model():
    from src.knowledge.index import index_samples
    from src.knowledge.store import VectorStore

    store = VectorStore(in_memory=True)
    index_samples(store)
    wrong = [q for exp, q in CALIBRATION if judge(q, store.search(q, k=12)).ok != exp]
    assert wrong == []
