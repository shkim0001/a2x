"""모니터링 규칙: 호출 로그 조회 범위와 오류 분류 (Python 코드로 판정).

조회 범위(화면 · Agent 공통):
- admin: 전체
- 그 외: 내가 담당하는 시스템이 클라이언트 또는 프로바이더인 호출 + 내가 직접 한 호출(MCP Tool)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.auth.models import User
from src.auth.repository import UserRepository
from src.monitoring.models import CallLog
from src.monitoring.repository import CallLogRepository
from src.shared.errors import Invalid, NotFound
from src.systems.access import is_admin
from src.systems.repository import SystemRepository


@dataclass(frozen=True)
class ErrorClass:
    category: str  # 원인 범주
    side: str  # 조치 주체: CLIENT(호출하는 쪽) | PROVIDER(대상 시스템) | PERMISSION(구독 · 권한)
    action: str


# 응답 코드 → 원인 범주 · 조치 (규칙). 없는 코드는 4xx면 400, 5xx면 500 규칙을 쓴다.
RULES: dict[int, ErrorClass] = {
    400: ErrorClass("요청 형식 오류", "CLIENT", "요청 레이아웃(필수 필드 · 타입)을 API 정의와 비교해 고치세요."),
    401: ErrorClass("인증 실패 · 토큰 만료", "CLIENT", "호출 시스템의 자격증명(토큰)을 갱신하세요. 만료 주기를 확인하고 자동 갱신을 설정하세요."),
    403: ErrorClass("권한 없음", "PERMISSION", "시스템 구독과 Tool 권한이 승인됐는지 확인하고, 없으면 포탈에서 신청하세요."),
    404: ErrorClass("리소스 없음", "CLIENT", "URL 패턴과 경로 파라미터 값을 API 정의와 비교하세요."),
    429: ErrorClass("호출 한도 초과", "CLIENT", "호출 빈도를 줄이고 재시도 간격(백오프)을 늘리세요. 한도 상향이 필요하면 대상 시스템 담당자에게 요청하세요."),
    500: ErrorClass("대상 시스템 내부 오류", "PROVIDER", "대상 시스템 담당자에게 해당 시각의 서버 로그 확인을 요청하세요."),
    502: ErrorClass("대상 시스템 연결 실패", "PROVIDER", "대상 시스템 서버 상태와 네트워크(방화벽)를 확인하세요."),
    504: ErrorClass("대상 시스템 응답 시간 초과", "PROVIDER", "대상 시스템 응답 지연입니다. 대상 시스템 상태를 확인하고, 호출 쪽 타임아웃 · 재시도 설정을 점검하세요."),
}


def classify(code: str | int) -> ErrorClass | None:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return RULES[500]
    if c < 400:
        return None
    return RULES.get(c) or (RULES[500] if c >= 500 else RULES[400])


def as_utc(dt: datetime) -> datetime:
    """SQLite는 시간대 없이 돌려주므로 UTC로 맞춘다."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def scope_for(db: Session, user: User) -> tuple[set[int], int] | None:
    return None if is_admin(user) else (SystemRepository(db).managed_ids(user.id), user.id)


def can_see(db: Session, user: User, log: CallLog) -> bool:
    scope = scope_for(db, user)
    if scope is None:
        return True
    ids, uid = scope
    return log.client_system_id in ids or log.provider_system_id in ids or log.user_id == uid


def get_log(db: Session, user: User, tx_id: str) -> CallLog:
    log = CallLogRepository(db).get_by_tx(tx_id)
    if log is None or not can_see(db, user, log):
        raise NotFound("트랜잭션을 찾을 수 없습니다.")
    return log


def list_logs(db: Session, user: User, **filters) -> list[CallLog]:
    # 저장 값은 UTC(SQLite는 시간대 없이 저장)이므로 기간도 UTC로 바꿔 비교한다
    for k in ("since", "until"):
        if filters.get(k) is not None:
            filters[k] = as_utc(filters[k])
    return CallLogRepository(db).search(scope=scope_for(db, user), **filters)


# ---------- 화면용 조회 · 집계 (T2-4) ----------
# 집계는 Python으로 한다(DB 방언 전용 날짜 함수를 쓰지 않음). 1차 데이터량(수만 건)에서는 충분하다.

KST = timezone(timedelta(hours=9))


def _kst(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(KST)


MAX_PERIOD_DAYS = 366  # 사용내역 · 일별 통계 조회 기간 상한
MAX_PERIOD_MONTHS = 36  # 월별 통계 조회 기간 상한


def _local(dt: datetime) -> datetime:
    """화면에서 온 시각: 시간대가 없으면 KST로 본다."""
    return dt.replace(tzinfo=KST) if dt.tzinfo is None else dt


def period(start: datetime | None, end: datetime | None, days: int, now: datetime) -> tuple[datetime, datetime]:
    """조회 기간(UTC). start · end가 없으면 최근 days일(끝은 지금). 끝이 시작보다 앞서거나 너무 길면 거절한다."""
    until = as_utc(_local(end)) if end else as_utc(now + timedelta(minutes=1))
    since = as_utc(_local(start)) if start else until - timedelta(days=days)
    if until <= since:
        raise Invalid("종료 시각은 시작 시각보다 뒤여야 합니다.", "invalid_period")
    if until - since > timedelta(days=MAX_PERIOD_DAYS):
        raise Invalid(f"조회 기간은 최대 {MAX_PERIOD_DAYS}일입니다.", "period_too_long")
    return since, until


def page_calls(db: Session, user: User, kind: str | None = None, status: str | None = None, q: str | None = None,
               days: int = 7, page: int = 1, size: int = 20, now: datetime | None = None,
               start: datetime | None = None, end: datetime | None = None) -> tuple[list[CallLog], int]:
    """사용내역 한 페이지(최신순)와 전체 건수. 조회 범위 · 기간(start~end 또는 최근 days일) · 상태 · 검색어 모두 DB에서 거른다."""
    now = now or datetime.now(timezone.utc)
    since, until = period(start, end, days, now)
    filters: dict = {"scope": scope_for(db, user), "since": since, "until": until,
                     "kind": kind, "failed_only": status == "failed", "success_only": status == "success"}
    if q and q.strip():
        ql = q.strip()
        sys_ids = {s.id for s in SystemRepository(db).search(q=ql)}
        user_ids = {u.id for u in UserRepository(db).search(ql, limit=200)}
        filters["text"] = (ql, sys_ids, user_ids)
    repo = CallLogRepository(db)
    total = repo.count_filtered(**filters)
    rows = repo.search(limit=size, offset=(max(page, 1) - 1) * size, **filters)
    return rows, total


def system_names(db: Session) -> dict[int, str]:
    return {s.id: s.name for s in SystemRepository(db).search()}


def user_names(db: Session, ids: set[int]) -> dict[int, tuple[str, str]]:
    """사용내역 표시용: 사용자 ID → (이름, 로그인 ID(이메일))."""
    repo = UserRepository(db)
    return {i: (u.name, u.email) for i in ids if (u := repo.get(i))}


def stats(db: Session, user: User, unit: str = "daily", now: datetime | None = None,
          start: date | None = None, end: date | None = None) -> list[dict]:
    """일별 · 월별 호출 · 오류 · 평균 응답시간(KST 기준). 기본은 일별 최근 30일 · 월별 최근 12개월,
    start · end(날짜, 월별은 그 날짜가 속한 달)를 주면 그 기간. 빈 기간도 0으로 채운다."""
    now = now or datetime.now(timezone.utc)
    today = _kst(now).date()
    if unit == "monthly":
        last = (end or today).replace(day=1)
        if start:
            first = start.replace(day=1)
        else:
            y, m = last.year, last.month - 11
            while m < 1:
                y, m = y - 1, m + 12
            first = date(y, m, 1)
        if first > last:
            raise Invalid("종료 월은 시작 월보다 같거나 뒤여야 합니다.", "invalid_period")
        keys, y, m = [], first.year, first.month
        while (y, m) <= (last.year, last.month):
            keys.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if len(keys) > MAX_PERIOD_MONTHS:
            raise Invalid(f"월별 조회 기간은 최대 {MAX_PERIOD_MONTHS}개월입니다.", "period_too_long")
        since = datetime(first.year, first.month, 1, tzinfo=KST)
        until = datetime(y, m, 1, tzinfo=KST)  # 마지막 달의 다음 달 1일
        key_of = lambda d: d.strftime("%Y-%m")  # noqa: E731
        label_of = lambda k: f"{k[2:4]}.{k[5:]}"  # noqa: E731
    else:
        last = end or today
        first = start or last - timedelta(days=29)
        if first > last:
            raise Invalid("종료일은 시작일보다 같거나 뒤여야 합니다.", "invalid_period")
        n = (last - first).days + 1
        if n > MAX_PERIOD_DAYS:
            raise Invalid(f"일별 조회 기간은 최대 {MAX_PERIOD_DAYS}일입니다.", "period_too_long")
        keys = [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
        since = datetime(first.year, first.month, first.day, tzinfo=KST)
        until = since + timedelta(days=n)
        key_of = lambda d: d.strftime("%Y-%m-%d")  # noqa: E731
        label_of = lambda k: f"{k[5:7]}/{k[8:]}" if first.year == last.year else f"{k[2:4]}/{k[5:7]}/{k[8:]}"  # noqa: E731
    acc = {k: {"api": 0, "mcp": 0, "errors": 0, "ms": 0} for k in keys}
    for r in list_logs(db, user, since=since, until=min(until, as_utc(now + timedelta(minutes=1))), limit=None):
        a = acc.get(key_of(_kst(r.started_at)))
        if a is None:
            continue
        a["api" if r.kind.value == "API" else "mcp"] += 1
        a["errors"] += 0 if r.success else 1
        a["ms"] += r.duration_ms
    return [
        {"key": k, "label": label_of(k), "api": a["api"], "mcp": a["mcp"], "errors": a["errors"],
         "avg_ms": round(a["ms"] / (a["api"] + a["mcp"])) if a["api"] + a["mcp"] else 0}
        for k, a in acc.items()
    ]


def summary(db: Session, user: User, now: datetime | None = None) -> dict:
    """메인 · 대시보드 · 왼쪽 패널용: 오늘 호출 · 오류, 최근 24시간 실패 수, 최근 24시간 오류 묶음 상위 3개."""
    now = now or datetime.now(timezone.utc)
    today = _kst(now).replace(hour=0, minute=0, second=0, microsecond=0)
    todays = list_logs(db, user, since=today, until=now + timedelta(minutes=1), limit=None)
    recent_failed = list_logs(db, user, since=now - timedelta(hours=24), until=now + timedelta(minutes=1), failed_only=True, limit=None)
    groups: dict[tuple[str, str], int] = {}
    for r in recent_failed:
        key = (r.name.split(" · ")[0], r.return_code)
        groups[key] = groups.get(key, 0) + 1
    top = sorted(groups.items(), key=lambda kv: -kv[1])[:3]
    errors_today = sum(not r.success for r in todays)
    return {
        "today_calls": len(todays),
        "today_errors": errors_today,
        "today_error_rate": round(errors_today / len(todays) * 100, 2) if todays else 0.0,
        "failed_24h": len(recent_failed),
        "recent_errors": [{"name": n, "code": c, "category": (classify(c).category if classify(c) else ""), "count": cnt} for (n, c), cnt in top],
    }
