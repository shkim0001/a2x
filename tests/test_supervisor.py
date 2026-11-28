"""T3-2 Supervisor 규칙 라우팅 (LLM 없이 결정적)."""

import json
from pathlib import Path

import pytest

from src.agents.supervisor import route

QUERIES = json.loads((Path(__file__).parent / "agent_queries.json").read_text(encoding="utf-8"))


def test_routing_accuracy_at_least_90_percent():
    rows = QUERIES["routing"]
    wrong = [(r["q"], r["route"], route(r["q"]).route) for r in rows if route(r["q"]).route != r["route"]]
    accuracy = 1 - len(wrong) / len(rows)
    assert accuracy >= 0.9, f"정확도 {accuracy:.0%}, 틀린 문장: {wrong}"


@pytest.mark.parametrize("row", QUERIES["context"], ids=lambda r: r["q"])
def test_context_rules(row):
    d = route(row["q"], page=row.get("page"), transaction_id=row.get("transaction_id"))
    assert d.route == row["route"] and d.rule.startswith(("context:", "howto:"))  # 가이드 질문은 화면 문맥보다 가이드 규칙


def test_command_strips_prefix_and_names_rule():
    d = route("/코드 고객 정보 MCP")
    assert (d.route, d.rule, d.message) == ("devsupport", "command:/코드", "고객 정보 MCP")


def test_default_and_deterministic():
    assert route("안녕하세요").rule == "default"
    assert [route("504 오류 원인").rule for _ in range(5)] == ["keywords:error"] * 5


def test_tie_prefers_error_over_others():
    # '등록'(자동화 2점)과 '실패'(오류 3점)가 함께 있으면 오류가 이긴다
    assert route("등록이 실패했어요").route == "error"
