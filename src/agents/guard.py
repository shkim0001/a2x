"""가드레일 (코드 판정). SERVICE.md 4절 · AGENTS.md 5절.

- check_request(전처리): 비밀 값 요구는 거절, 승인 · 반려 · 해지 · 삭제 같은 변경 요청은 안내만(Agent에 쓰기 Tool 없음).
  제출 요청은 막지 않고 표시만 해 두었다가 응답에 '제출은 직접'을 덧붙인다.
- sanitize(후처리): 응답 · 제안 값 · 출처에서 토큰 · 비밀번호 · 키와 개인정보(주민번호 · 휴대전화 · 카드번호)를 가린다.
  설정(.env)의 실제 비밀 값이 그대로 나오면 그것도 가린다. 이메일(사내 담당자 안내)은 가리지 않는다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.agents.state import AgentResult
from src.shared.config import settings

SECRET_WORDS = r"(토큰|비밀\s?번호|패스워드|password|api\s?키|api\s?key|시크릿|secret|자격\s?증명|인증\s?키|접속\s?정보)"
ASK_VALUE = r"(값|알려|보여|공유|뭐야|뭔가요|줘|주세요)"
LEGIT = r"(코드|예시|샘플|방법|어떻게|발급|갱신|만료|넣|설정|관리|보관|절차|오류|에러|실패)"
WRITE_ACTS = r"(승인|반려|해지|삭제|취소|중지|재개|운영\s?전환)\s?(해\s?줘|해\s?주세요|해|처리|시켜|하라|좀)"
SUBMIT = r"제출|승인\s?요청까지|바로\s?(등록|신청)"

MASKS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(Bearer\s+)(?![<*])[A-Za-z0-9._~+/=-]{8,}"), r"\1****"),
    (re.compile(r"\b(sk-ant-|sk-|ghp_|xox[bp]-)[A-Za-z0-9_-]{12,}"), "****"),
    (re.compile(r"(?i)\b((?:password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret)\"?\s*[=:]\s*[\"']?)(?![<*])[^\s\"',}<]{4,}"), r"\1****"),
    (re.compile(r"(?<!\d)(\d{6})-[1-4]\d{6}(?!\d)"), r"\1-*******"),  # 주민등록번호
    (re.compile(r"(?<!\d)(01[016789])-?\d{3,4}-?(\d{4})(?!\d)"), r"\1-****-\2"),  # 휴대전화
    (re.compile(r"(?<!\d)\d{4}-\d{4}-\d{4}-(\d{4})(?!\d)"), r"****-****-****-\1"),  # 카드번호
]


@dataclass
class RequestCheck:
    blocked: AgentResult | None = None
    notes: list[str] = field(default_factory=list)
    wants_submit: bool = False


def check_request(message: str) -> RequestCheck:
    t = message.lower()
    if re.search(SECRET_WORDS, t) and re.search(ASK_VALUE, t) and not re.search(LEGIT, t):
        return RequestCheck(
            blocked=AgentResult(
                answer="토큰 · 비밀번호 · 키 같은 비밀 값은 Agent가 알려 드리지 않습니다. 원본 API 인증 정보는 프로바이더 시스템 담당자에게 정식으로 발급받고, "
                       "코드에는 환경변수로 넣어 주세요. 발급 절차나 넣는 방법은 안내해 드릴 수 있습니다.",
            ),
            notes=["blocked:secret"],
        )
    if re.search(WRITE_ACTS, t):
        return RequestCheck(
            blocked=AgentResult(
                answer="Agent는 승인 · 반려 · 해지 같은 변경을 하지 않습니다. 권한이 있는 담당자가 구독 · 승인 화면에서 직접 처리해 주세요. "
                       "승인 권한은 대상(프로바이더) 시스템 담당자에게 있습니다.",
                actions=[{"type": "open", "page": "subscriptions", "label": "구독 · 승인 화면 열기"}],
            ),
            notes=["blocked:write"],
        )
    if re.search(SUBMIT, t):
        return RequestCheck(notes=["submit_requested"], wants_submit=True)
    return RequestCheck()


def _env_secrets() -> list[str]:
    vals = [settings.ANTHROPIC_API_KEY or "", settings.SECRET_KEY]
    vals += [v for k, v in os.environ.items() if k.startswith("A2X_UPSTREAM_TOKEN_") or k == "ANTHROPIC_API_KEY"]
    return [v for v in vals if v and len(v) >= 8]


def mask_text(text: str, secrets: list[str] | None = None) -> tuple[str, int]:
    n = 0
    for s in secrets if secrets is not None else _env_secrets():
        if s in text:
            n += text.count(s)
            text = text.replace(s, "****")
    for pat, rep in MASKS:
        text, k = pat.subn(rep, text)
        n += k
    return text, n


def _walk(v: Any, secrets: list[str], count: list[int]) -> Any:
    if isinstance(v, str):
        out, n = mask_text(v, secrets)
        count[0] += n
        return out
    if isinstance(v, list):
        return [_walk(x, secrets, count) for x in v]
    if isinstance(v, dict):
        return {k: _walk(x, secrets, count) for k, x in v.items()}
    return v


def sanitize(result: AgentResult, check: RequestCheck | None = None) -> tuple[AgentResult, list[str]]:
    secrets, count = _env_secrets(), [0]
    result.answer = _walk(result.answer, secrets, count)
    result.sources = _walk(result.sources, secrets, count)
    result.form_suggestion = _walk(result.form_suggestion, secrets, count)
    notes = [f"masked:{count[0]}"] if count[0] else []
    if check and check.wants_submit and "제출은 하지 않았습니다" not in result.answer:
        result.answer += "\n\nAgent는 등록 · 신청을 제출하지 않습니다. 화면에서 내용을 확인한 뒤 직접 제출해 주세요."
        notes.append("no_submit")
    return result, notes
