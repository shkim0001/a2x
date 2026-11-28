"""T2-3 2단계 구독 · Tool 신청 · 승인 · 해지 · 권한 확인."""

API = "/api/v1"
HONG, ADMIN, KIM, LEE = "hong@example.com", "admin@example.com", "kim@example.com", "lee@example.com"
KANG = "kang@example.com"  # PURCH(구매 추천 Agent) 담당
SEO = "seo@example.com"  # MKT(마케팅 분석 Agent) 담당
YOON = "yoon@example.com"  # CS 챗봇 담당(공동)
PLAN = "park.plan@example.com"


def asset_id(client, h, name):
    return next(a["id"] for a in client.get(f"{API}/assets?q={name}", headers=h).json() if a["name"] == name)


def sys_id(client, h, code):
    return next(s["id"] for s in client.get(f"{API}/systems", headers=h).json() if s["code"] == code)


def sub_id(client, h, client_code, asset_name, scope="requested"):
    return next(s["id"] for s in client.get(f"{API}/subscriptions?scope={scope}", headers=h).json() if s["client_system"]["code"] == client_code and s["asset"]["name"] == asset_name)


# ---------- 1) 시스템 구독 ----------


def test_request_subscription_and_provider_approves(client, as_user):
    seo = as_user(SEO)
    r = client.post(f"{API}/subscriptions", headers=seo, json={"client_system_id": sys_id(client, seo, "MKT"), "asset_id": asset_id(client, seo, "공급사 정보 MCP"), "purpose": "공급사별 프로모션"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["status"] == "PENDING" and r.json()["provider_system"]["code"] == "SCM"

    # 승인은 프로바이더(SCM) 담당자 또는 admin(신청자 쪽 담당자는 불가)
    assert client.post(f"{API}/subscriptions/{sid}/approve", headers=seo).status_code == 403
    admin_queue = client.get(f"{API}/subscriptions?scope=approve&status=PENDING", headers=as_user(ADMIN)).json()
    assert next(x for x in admin_queue if x["id"] == sid)["can_decide"] is True
    oh = as_user("oh.scm@example.com")
    queue = client.get(f"{API}/subscriptions?scope=approve&status=PENDING", headers=oh).json()
    assert [s["id"] for s in queue] == [sid] and queue[0]["can_decide"] is True
    r = client.post(f"{API}/subscriptions/{sid}/approve", headers=oh, json={"note": "확인"})
    assert r.json()["status"] == "APPROVED" and r.json()["decision_note"] == "확인"
    assert client.post(f"{API}/subscriptions/{sid}/approve", headers=oh).json()["code"] == "not_pending"


def test_subscription_rules(client, as_user):
    h = as_user(HONG)
    csbot, wms = sys_id(client, h, "CSBOT"), sys_id(client, h, "WMS")
    cases = [
        ({"client_system_id": csbot, "asset_id": asset_id(client, h, "재고 MCP 서버"), "purpose": "x"}, 409, "already_subscribed"),
        ({"client_system_id": wms, "asset_id": asset_id(client, h, "입출고 API"), "purpose": "x"}, 422, "self_subscription"),
        ({"client_system_id": csbot, "asset_id": asset_id(client, h, "수요 예측 API"), "purpose": "x"}, 422, "asset_not_live"),
        ({"client_system_id": csbot, "asset_id": asset_id(client, h, "근태 조회 API"), "purpose": "  "}, 422, "purpose_required"),
        ({"client_system_id": sys_id(client, h, "MKT"), "asset_id": asset_id(client, h, "근태 조회 API"), "purpose": "x"}, 403, "not_client_manager"),
    ]
    for body, status, code in cases:
        r = client.post(f"{API}/subscriptions", headers=h, json=body)
        assert (r.status_code, r.json()["code"]) == (status, code), (body, r.text)


def test_rejected_subscription_can_be_requested_again(client, as_user):
    seo = as_user(SEO)  # MKT → 재고 MCP는 시드에서 반려 상태
    r = client.post(f"{API}/subscriptions", headers=seo, json={"client_system_id": sys_id(client, seo, "MKT"), "asset_id": asset_id(client, seo, "재고 MCP 서버"), "purpose": "재신청"})
    assert r.status_code == 201


def test_scopes(client, as_user):
    h = as_user(HONG)
    approve = client.get(f"{API}/subscriptions?scope=approve", headers=h).json()
    assert all(s["provider_system"]["code"] == "WMS" for s in approve)
    requested = client.get(f"{API}/subscriptions?scope=requested", headers=h).json()
    assert {s["client_system"]["code"] for s in requested} == {"CSBOT"}
    assert client.get(f"{API}/subscriptions?scope=all", headers=h).status_code == 403
    assert len(client.get(f"{API}/subscriptions?scope=all", headers=as_user(ADMIN)).json()) == 17
    assert [s["asset"]["name"] for s in client.get(f"{API}/subscriptions?scope=requested&q=상담 이력", headers=h).json()] == ["상담 이력 MCP"]


def test_cancel_subscription_cascades_tool_permissions(client, as_user):
    h = as_user(HONG)
    sid = sub_id(client, h, "CSBOT", "재고 MCP 서버")  # 홍길동 get_stock 승인, 김민수 reserve_stock 대기
    assert client.post(f"{API}/subscriptions/{sid}/cancel", headers=as_user(KIM)).status_code == 403
    r = client.post(f"{API}/subscriptions/{sid}/cancel", headers=h)
    assert r.json()["status"] == "CANCELLED"
    statuses = {t["tool"]["name"]: t["status"] for t in client.get(f"{API}/tool-requests?scope=all", headers=as_user(ADMIN)).json() if t["subscription_id"] == sid}
    assert set(statuses.values()) == {"CANCELLED"}
    assert client.get(f"{API}/permissions/check?subscription_id={sid}&tool=get_stock", headers=h).json()["allowed"] is False


# ---------- 2) Tool 사용 신청 ----------


def test_user_requests_tools_and_provider_approves(client, as_user):
    lee = as_user(LEE)
    conns = client.get(f"{API}/connections", headers=lee).json()
    stock = next(c for c in conns if c["asset"]["name"] == "재고 MCP 서버")
    assert {t["name"]: t["my_status"] for t in stock["tools"]}["get_stock"] == "APPROVED"  # 시드: 이영희 get_stock 승인

    r = client.post(f"{API}/tool-requests", headers=lee, json={"subscription_id": stock["subscription_id"], "tools": ["get_stock", "list_warehouses", "list_warehouses"], "purpose": "창고 확인"})
    assert r.status_code == 201
    assert [t["tool"]["name"] for t in r.json()["created"]] == ["list_warehouses"] and r.json()["skipped"] == ["get_stock"]
    trid = r.json()["created"][0]["id"]

    sid = stock["subscription_id"]
    assert client.get(f"{API}/permissions/check?subscription_id={sid}&tool=list_warehouses", headers=lee).json()["allowed"] is False
    # 승인은 프로바이더(WMS) 담당자. 클라이언트(CS 챗봇) 공동 담당자 윤상담은 불가
    assert client.post(f"{API}/tool-requests/{trid}/approve", headers=as_user(YOON)).status_code == 403
    assert client.post(f"{API}/tool-requests/{trid}/approve", headers=as_user("choi@example.com")).json()["status"] == "APPROVED"
    assert client.get(f"{API}/permissions/check?subscription_id={sid}&tool=list_warehouses", headers=lee).json() == {"allowed": True, "reason": "허용"}


def test_tool_request_rules(client, as_user):
    kim = as_user(KIM)
    admin = as_user(ADMIN)
    all_subs = client.get(f"{API}/subscriptions?scope=all", headers=admin).json()
    api_sub = next(s for s in all_subs if s["asset"]["type"] == "API" and s["status"] == "APPROVED")
    pending_sub = next(s for s in all_subs if s["status"] == "PENDING" and s["asset"]["type"] == "MCP")
    stock = next(s for s in all_subs if s["asset"]["name"] == "재고 MCP 서버" and s["status"] == "APPROVED")
    cases = [
        ({"subscription_id": api_sub["id"], "tools": ["x"], "purpose": "p"}, "not_mcp"),
        ({"subscription_id": pending_sub["id"], "tools": ["get_stock"], "purpose": "p"}, "subscription_not_approved"),
        ({"subscription_id": stock["id"], "tools": ["nope"], "purpose": "p"}, "unknown_tool"),
        ({"subscription_id": stock["id"], "tools": ["get_stock"], "purpose": " "}, "purpose_required"),
    ]
    for body, code in cases:
        r = client.post(f"{API}/tool-requests", headers=kim, json=body)
        assert r.status_code == 422 and r.json()["code"] == code, (body, r.text)


def test_hidden_tool_cannot_be_requested(client, as_user, session_factory):
    from src.catalog.models import McpTool

    with session_factory() as s:
        t = s.query(McpTool).filter(McpTool.name == "list_warehouses").one()
        t.exposed = False
        s.commit()
    lee = as_user(LEE)
    sid = next(c["subscription_id"] for c in client.get(f"{API}/connections", headers=lee).json() if c["asset"]["name"] == "재고 MCP 서버")
    r = client.post(f"{API}/tool-requests", headers=lee, json={"subscription_id": sid, "tools": ["list_warehouses"], "purpose": "p"})
    assert r.json()["code"] == "unknown_tool"


def test_my_requests_and_cancel(client, as_user):
    h = as_user(HONG)
    mine = client.get(f"{API}/tool-requests?scope=mine", headers=h).json()
    assert {t["tool"]["name"] for t in mine} == {"get_approval_line", "get_stock", "get_org", "get_consult_history", "create_followup",
                                                 "search_systems", "get_system", "search_servers"}  # A2X Agent 조회 Tool(담당자 일괄 승인)
    pending = next(t for t in mine if t["tool"]["name"] == "create_followup")
    assert pending["can_cancel"] is True
    assert client.post(f"{API}/tool-requests/{pending['id']}/cancel", headers=as_user(KIM)).status_code == 403
    assert client.post(f"{API}/tool-requests/{pending['id']}/cancel", headers=h).json()["status"] == "CANCELLED"
    # 해지한 Tool은 다시 신청할 수 있다
    r = client.post(f"{API}/tool-requests", headers=h, json={"subscription_id": pending["subscription_id"], "tools": ["create_followup"], "purpose": "재신청"})
    assert len(r.json()["created"]) == 1


def test_provider_queue_and_reject(client, as_user):
    h = as_user(HONG)
    queue = client.get(f"{API}/tool-requests?scope=approve&status=PENDING", headers=h).json()
    assert [(t["user"]["name"], t["tool"]["name"]) for t in queue] == [("김민수", "reserve_stock")]
    r = client.post(f"{API}/tool-requests/{queue[0]['id']}/reject", headers=h, json={"note": "변경 Tool은 팀장 승인 필요"})
    assert r.json()["status"] == "REJECTED" and r.json()["can_decide"] is False


def test_requested_scope_for_agent_manager(client, as_user):
    plan = as_user(PLAN)
    rows = client.get(f"{API}/tool-requests?scope=requested", headers=plan).json()
    assert {r["user"]["name"] for r in rows} == {"박계획", "정현장"}
    assert all(r["client_system"]["code"] == "PLAN" for r in rows)


def test_subscription_flow_end_to_end(client, as_user):
    """PLAN Agent가 설비 MCP와 연계 → 사용자 신청 → 승인 → 호출 허용."""
    kang = as_user(KANG)
    # PURCH(구매 추천 Agent) → 설비 상태 MCP 구독 신청 → MES 담당자 승인
    r = client.post(f"{API}/subscriptions", headers=kang, json={"client_system_id": sys_id(client, kang, "PURCH"), "asset_id": asset_id(client, kang, "설비 상태 MCP"), "purpose": "설비 가동률 기반 발주"})
    sid = r.json()["id"]
    client.post(f"{API}/subscriptions/{sid}/approve", headers=as_user("moon.mes@example.com"))
    # 일반 사용자가 Tool 신청 → MES 담당자 승인
    kim = as_user(KIM)
    trid = client.post(f"{API}/tool-requests", headers=kim, json={"subscription_id": sid, "tools": ["get_oee"], "purpose": "라인 효율"}).json()["created"][0]["id"]
    client.post(f"{API}/tool-requests/{trid}/approve", headers=as_user("bae.mes@example.com"))
    assert client.get(f"{API}/permissions/check?subscription_id={sid}&tool=get_oee", headers=kim).json()["allowed"] is True
    assert client.get(f"{API}/permissions/check?subscription_id={sid}&tool=reset_alarm", headers=kim).json()["allowed"] is False
