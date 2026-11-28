"""T3-6 오류 조치 Agent: 시드 DB + 고정 시각의 샘플 호출 로그(T1-2 생성기). LLM 없이 규칙만으로."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import anyio
import pytest

from src.agents.error_action import agent as ea
from src.auth.repository import UserRepository
from src.monitoring.generator import generate, KST
from src.monitoring.models import CallLog
from src.monitoring.service import as_utc, classify
from src.tools.portal import PortalTools

NOW = datetime(2026, 11, 25, 15, 0, tzinfo=KST)  # 수요일


@pytest.fixture()
def db(seeded):
    generate(seeded, days=7, now=NOW)
    seeded.commit()
    return seeded


def portal(db, email):
    return PortalTools(db, UserRepository(db).get_by_email(email))


def run(p, message, tx=None, llm=None):
    return anyio.run(lambda: ea.run(message, p, llm=llm, transaction_id=tx, now=NOW))


def first_log(db, code, **where):
    q = db.query(CallLog).filter(CallLog.return_code == code)
    for k, v in where.items():
        q = q.filter(getattr(CallLog, k) == v)
    return q.order_by(CallLog.started_at).first()


def test_classify_rules():
    assert classify("200") is None
    assert classify(403).side == "PERMISSION" and classify(504).side == "PROVIDER"
    assert classify(418).category == "요청 형식 오류" and classify(503).category == "대상 시스템 내부 오류"


def test_parse_period_and_filters():
    s, u, label = ea.parse_period("어제 오류 알려줘", NOW)
    assert label == "어제" and s == datetime(2026, 11, 24, tzinfo=KST) and u == datetime(2026, 11, 25, tzinfo=KST)
    assert ea.parse_period("최근 3일", NOW)[0] == NOW - timedelta(days=3)
    assert ea.parse_period("오류 있어?", NOW)[2] == "최근 24시간"
    f = ea.parse_filters("WMS 429 오류 API만", [{"id": 2, "code": "WMS", "name": "WMS"}, {"id": 1, "code": "ERP", "name": "ERP"}])
    assert f == {"codes": {"429"}, "kind": "API", "system_ids": {2}}


def test_summary_finds_provider_outage(db):
    r = run(portal(db, "admin@example.com"), "그제 오류 원인 정리해줘")
    top = r.answer.split("\n- ")[1]
    assert "504 대상 시스템 응답 시간 초과" in top and "11/23 10시대" in top and "대상 시스템 문제 가능성" in top
    assert "담당자:" in top
    assert "TX-20261124" not in r.answer  # 기간 밖(KST 기준) 건은 섞이지 않는다


def test_summary_finds_repeated_429(db):
    r = run(portal(db, "admin@example.com"), "어제 429 오류")
    assert "어제 · 응답 429" in r.answer and "같은 연계(구독 #" in r.answer and "반복" in r.answer


def test_scope_user_sees_only_own_calls(db):
    kim = portal(db, "kim@example.com")
    uid = kim.user.id
    assert all(x["user_id"] == uid for x in kim.query_call_logs(since=NOW - timedelta(days=7)))
    other = first_log(db, "504", kind="API")  # API 호출(사용자 없음)은 kim의 범위 밖
    r = run(kim, "이거 왜 실패했어?", tx=other.tx_id)
    assert "찾을 수 없거나 조회 권한이 없습니다" in r.answer


def test_diagnose_403_checks_tool_request(db):
    log = first_log(db, "403")
    r = run(portal(db, "admin@example.com"), "왜 실패?", tx=log.tx_id)
    assert "권한 없음" in r.answer and "사용자 Tool 권한 확인" in r.answer
    assert any(s in r.answer for s in ("승인 대기 중", "반려됐습니다"))
    # 권한 거부: 그 MCP 서버를 담은 카탈로그 사용 신청 화면으로 안내
    assert any(a["type"] == "request" and a["asset_id"] for a in r.actions)


def test_diagnose_504_in_outage_window(db):
    log = db.query(CallLog).filter(CallLog.return_code == "504").all()
    in_burst = next(x for x in log if as_utc(x.started_at).astimezone(KST).date() == (NOW - timedelta(days=2)).date() and as_utc(x.started_at).astimezone(KST).hour == 10)
    r = run(portal(db, "admin@example.com"), f"{in_burst.tx_id} 원인 알려줘")  # 메시지 안의 TX ID
    assert "대상 시스템 장애일 가능성이 높습니다" in r.answer and "대상 시스템 담당자" in r.answer


def test_success_tx(db):
    log = first_log(db, "200")
    r = run(portal(db, "admin@example.com"), "이 건 확인", tx=log.tx_id)
    assert "성공한 호출입니다" in r.answer and "**조치**" not in r.answer


def test_no_failures(db):
    r = run(portal(db, "admin@example.com"), "오늘 418 오류")
    assert "실패한 호출이 없습니다" in r.answer


def test_llm_gets_numbers_without_contacts(db):
    sent = []

    class FakeLLM:
        available = True

        def complete(self, messages, system=None, **kw):
            sent.append(messages[0]["content"])
            return SimpleNamespace(text="ERP 담당자에게 장애 확인을 먼저 요청하세요.", model="claude-sonnet-5-5")

    r = run(portal(db, "admin@example.com"), "그제 오류 정리", llm=FakeLLM())
    assert r.used_llm == "claude-sonnet-5-5" and "장애 확인을 먼저" in r.answer
    assert "@example.com" not in sent[0] and '"count": 16' in sent[0]
