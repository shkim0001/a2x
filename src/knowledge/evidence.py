"""근거 판정 규칙 (코드). 임베딩 유사도만으로는 '문서에 답이 있는가'를 가르기 어렵다.

실측(다국어 MiniLM, 샘플 문서):
- 답이 있는 '운영 상태가 되려면 어떤 절차를 거치나요'는 정답 청크(등록 절차)가 0.10으로 6위였다.
- 답이 없는 '화성 탐사선 API 연계 표준이 뭐야'는 일반어(API · 연계 · 표준) 때문에 0.41이 나왔다.
그래서
  1) 재정렬: 넓게(pool) 뽑은 뒤 '유사도 + 청크 안 핵심어 비율'로 다시 순위를 매긴다(하이브리드).
  2) 판정: 근거 후보 = 유사도 ≥ RAG_MIN_SCORE 이거나 청크 핵심어 비율 ≥ RAG_MIN_COVERAGE 인 청크.
     (후보가 있고 후보 전체의 핵심어 포함률 ≥ RAG_MIN_COVERAGE) 또는 최고 유사도 ≥ RAG_STRONG_SCORE 이면 근거 있음.
핵심어: 질문 단어에서 조사 · 어미 · 일반어(STOPWORDS)를 뺀 것.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.knowledge.store import Hit
from src.shared.config import settings

# 질문에 흔히 붙지만 근거 여부와 상관없는 말(일반어 · 질문 표현 · 도메인 공통어)
STOPWORDS = {
    "뭐야", "무엇", "무엇인가요", "뭔가요", "어떻게", "어떤", "알려줘", "알려주세요", "궁금", "궁금해요", "궁금합니다",
    "해요", "하나요", "되나요", "있나요", "좋아요", "좋나요", "할까요", "해야", "하는", "있는", "없는", "대해", "관련",
    "방법", "방식", "경우", "때", "중", "좀", "그리고", "또는", "우리", "회사", "사내", "시스템", "api", "mcp", "a2a",
    "연계", "연동", "agent", "에이전트", "문서", "내용", "설명", "추천", "해줘", "주세요", "인가요", "가요", "나요", "좋아", "좋은", "어떨까", "알려", "가이드", "표준",
}
PARTICLES = ("에서는", "으로는", "에서", "으로", "까지", "부터", "에게", "이랑", "랑", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "요")
# 동사 · 형용사 어미: 떼고 남은 말(어간 · 명사)만 본다. 예: 변환할 → 변환, 반복되면 → 반복, 하나요 → (없음)
ENDINGS = ("하나요", "되나요", "인가요", "합니까", "되려면", "하려면", "려면", "되면", "하면", "해야", "해요", "해줘", "하는", "하나", "되나", "어야", "아요", "나", "할", "한", "해", "야", "줘")


@dataclass
class Evidence:
    ok: bool
    top_score: float
    coverage: float
    keywords: list[str]
    missing: list[str]
    hits: list[Hit]


def keywords(question: str) -> list[str]:
    out = []
    for tok in re.findall(r"[가-힣A-Za-z0-9]+", question.lower()):
        for p in PARTICLES:  # 조사 떼기(가장 긴 것부터)
            if tok.endswith(p) and len(tok) - len(p) >= 2:
                tok = tok[: -len(p)]
                break
        for e in ENDINGS:  # 어미 떼기: 남은 말이 한 글자 이하면 버린다
            if tok.endswith(e):
                tok = tok[: -len(e)]
                break
        if len(tok) >= 2 and tok not in STOPWORDS and not tok.isdigit():
            out.append(tok)
    return list(dict.fromkeys(out))


KW_WEIGHT = 0.4  # 재정렬 점수 = (1 - KW_WEIGHT) * 유사도 + KW_WEIGHT * 청크 핵심어 비율


def _ratio(kws: list[str], text: str) -> float:
    return sum(k in text for k in kws) / len(kws) if kws else 0.0


def judge(question: str, hits: list[Hit], k: int = 4) -> Evidence:
    """hits: store.search(question, k=pool)의 결과(넓게). 근거로 쓸 상위 k개를 골라 돌려준다."""
    kws = keywords(question)
    scored = [(h, _ratio(kws, (h.text + " " + h.section).lower())) for h in hits]
    scored.sort(key=lambda x: (1 - KW_WEIGHT) * x[0].score + KW_WEIGHT * x[1], reverse=True)
    good = [h for h, r in scored if h.score >= settings.RAG_MIN_SCORE or (kws and r >= settings.RAG_MIN_COVERAGE)][:k]
    top = max((h.score for h in hits), default=0.0)
    corpus = " ".join((h.text + " " + h.section).lower() for h in good)
    present = [w for w in kws if w in corpus]
    coverage = len(present) / len(kws) if kws else 1.0
    ok = bool(good) and (coverage >= settings.RAG_MIN_COVERAGE or top >= settings.RAG_STRONG_SCORE)
    return Evidence(ok=ok, top_score=top, coverage=round(coverage, 2), keywords=kws, missing=[w for w in kws if w not in present], hits=good if ok else [])
