"""Supervisor: 규칙 기반 라우팅 (AGENTS.md 2.1). LLM을 쓰지 않는다 — 같은 입력이면 항상 같은 결과.

우선순위: 1) 명시 지정(/명령) 2) 화면 문맥 3) 키워드 점수 4) 기본값(컨설팅)
결과에 일치한 규칙 이름을 남겨 재현 · 감사할 수 있게 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Route = Literal["consult", "automation", "devsupport", "error"]
ROUTES: tuple[Route, ...] = ("consult", "automation", "devsupport", "error")
ROUTE_LABEL: dict[Route, str] = {"consult": "컨설팅", "automation": "프로세스 자동화", "devsupport": "개발 지원", "error": "오류 조치"}

COMMANDS: dict[str, Route] = {"/컨설팅": "consult", "/자동채움": "automation", "/채움": "automation", "/코드": "devsupport", "/개발": "devsupport", "/오류": "error"}

# 키워드 사전: (패턴, 가중치). 패턴은 정규식이며 대소문자를 무시한다.
KEYWORDS: dict[Route, list[tuple[str, int]]] = {
    "error": [
        (r"오류|에러|error|실패|장애|안\s?돼|안\s?됨|안됩니다|거부|denied|차단", 3),
        (r"타임아웃|timeout|time\s?out|지연|느려", 3),
        (r"(?<!\d)(4\d\d|5\d\d)(?!\d)", 3),  # 한글이 바로 붙어도("504가") 인식
        (r"원인|왜\s|조치|해결", 1),
    ],
    "automation": [
        (r"채워|채우|자동\s?채움|자동\s?입력|입력해|작성해|대신\s?신청|신청서", 3),
        (r"등록|신청|구독", 2),
        (r"마스터|양식|폼|form", 1),
    ],
    "devsupport": [
        (r"코드|예시|예제|샘플|sample|snippet|스니펫", 3),
        (r"curl|python|파이썬|java|자바|typescript|sdk|클라이언트|client", 3),
        (r"설정|config|연동\s?방법|접속\s?방법|호출\s?방법|헤더|header", 2),
    ],
    "consult": [
        (r"어떤\s?방식|어떻게\s?연계|추천|권장|가능한가|가능할까|가능해|차이|비교|장단점", 3),
        (r"가이드|표준|정책|규정|절차|기준|보안|체크리스트", 2),
        (r"궁금|알려\s?줘|뭐야|무엇|뭔가요", 2),  # 질문 표현
        (r"API|MCP|A2A|변환", 1),
    ],
}

# '어떻게 하는지' 묻는 질문(가이드)과 '해 달라'는 요청을 구분한다.
# 예: "시스템 등록은 어떻게 해?"(가이드 → 컨설팅) vs "QMS 시스템 등록 채워줘"(요청 → 자동화)
HOWTO = r"어떻게|방법|절차|순서|가이드|하려면|어디서|어디에서|할\s?수\s?있|뭘\s?해야|무엇을\s?해야|하는\s?(법|거|건지)|되는\s?(거|건지)"
REQUEST = r"채워|채우|작성해|입력해\s?줘|넣어\s?줘|대신|해\s?줘|해\s?주세요|해\s?줄래"


def is_howto(text: str) -> bool:
    return bool(re.search(HOWTO, text)) and not re.search(REQUEST, text)


# 화면 문맥: 이 화면에서 이런 말이면 이 Agent
AUTOFILL_PAGES = {"publish", "mcp-register", "catalog", "systems"}
ERROR_PAGES = {"usage-api", "usage-mcp", "stats"}


@dataclass
class RouteDecision:
    route: Route
    rule: str  # 일치한 규칙 이름
    scores: dict[str, int] = field(default_factory=dict)
    message: str = ""  # 명령어를 뗀 본문

    @property
    def label(self) -> str:
        return ROUTE_LABEL[self.route]


def score(text: str) -> dict[Route, int]:
    return {r: sum(w * len(re.findall(p, text, flags=re.IGNORECASE)) for p, w in pats) for r, pats in KEYWORDS.items()}


def route(message: str, page: str | None = None, transaction_id: str | None = None) -> RouteDecision:
    text = message.strip()

    # 1) 명시 지정
    for cmd, r in COMMANDS.items():
        if text.startswith(cmd):
            return RouteDecision(r, f"command:{cmd}", message=text[len(cmd):].strip())

    s = score(text)

    # 2) 화면 문맥
    if transaction_id and page in ERROR_PAGES:
        return RouteDecision("error", "context:transaction", s, text)
    howto = is_howto(text)
    if page in AUTOFILL_PAGES and re.search(r"채워|채우|자동|입력|작성", text) and not howto:
        return RouteDecision("automation", f"context:page={page}", s, text)

    # 3) 키워드 점수 (동점이면 오류 → 자동화 → 개발 지원 → 컨설팅 순으로 우선)
    best = max(s.values())
    if best > 0:
        tie_order: list[Route] = ["error", "automation", "devsupport", "consult"]
        winner = next(r for r in tie_order if s[r] == best)
        if winner == "automation" and howto:  # 등록 · 신청 '방법'을 묻는 질문은 실제 채움이 아니라 사용 가이드
            return RouteDecision("consult", "howto:guide", s, text)
        return RouteDecision(winner, f"keywords:{winner}", s, text)

    # 4) 기본값
    return RouteDecision("consult", "default", s, text)
