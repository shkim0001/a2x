"""T2-2 시스템 · 서버 · API · MCP 등록 API."""

API = "/api/v1"
HONG, ADMIN, KIM, CHOI = "hong@example.com", "admin@example.com", "kim@example.com", "choi@example.com"


def _sys_id(client, h, code):
    return next(s["id"] for s in client.get(f"{API}/systems", headers=h).json() if s["code"] == code)


def api_body(system_id, **kw):
    body = {
        "system_id": system_id,
        "name": "재고 이력 API",
        "business": {"category": "물류", "name": "재고 이력", "program": "WMS_HIS", "impact": "HIGH"},
        "base_url": "https://wms.internal.example/api/v2",
        "auth_type": "OAuth2 Client Credentials",
        "operations": [{"method": "GET", "path": "/stock-history", "summary": "이력 목록"}, {"method": "GET", "path": "/stock-history/{itemId}", "summary": "이력 상세"}],
        "request_layout": [{"name": "itemId", "type": "string", "required": True}],
        "response_layout": [{"name": "items[].qty", "type": "integer"}],
        "icon": {"name": "warehouse", "color": "#0071e3"},
    }
    body.update(kw)
    return body


# ---------- 시스템 ----------


def test_create_system_makes_creator_manager_and_promotes(client, as_user):
    h = as_user(KIM)  # 일반 사용자
    r = client.post(f"{API}/systems", headers=h, json={"code": "qms", "name": "품질관리시스템", "kind": "BUSINESS", "process": "생산", "manager_emails": [CHOI], "servers": [{"hostname": "qms-01", "ip": "10.1.1.1", "port": 8080}]})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["code"] == "QMS" and {m["email"] for m in s["managers"]} == {KIM, CHOI}
    assert client.get(f"{API}/auth/me", headers=h).json()["effective_role"] == "MANAGER"
    dup = client.post(f"{API}/systems", headers=h, json={"code": "QMS", "name": "x", "kind": "BUSINESS", "process": "생산"})
    assert dup.status_code == 409


def test_only_managers_can_update_system(client, as_user):
    wms = _sys_id(client, as_user(HONG), "WMS")
    assert client.patch(f"{API}/systems/{wms}", headers=as_user(KIM), json={"dept": "x"}).status_code == 403
    r = client.patch(f"{API}/systems/{wms}", headers=as_user(HONG), json={"dept": "물류플랫폼팀"})
    assert r.status_code == 200 and r.json()["dept"] == "물류플랫폼팀"
    assert client.patch(f"{API}/systems/{wms}", headers=as_user(ADMIN), json={"dept": "admin 수정"}).status_code == 200


def test_add_and_remove_manager(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    r = client.post(f"{API}/systems/{wms}/managers", headers=h, json={"email": KIM})
    assert r.status_code == 200 and KIM in {m["email"] for m in r.json()["managers"]}
    assert client.post(f"{API}/systems/{wms}/managers", headers=h, json={"email": KIM}).status_code == 409
    assert client.post(f"{API}/systems/{wms}/managers", headers=h, json={"email": "none@example.com"}).status_code == 404
    kim_id = next(m["id"] for m in r.json()["managers"] if m["email"] == KIM)
    assert client.delete(f"{API}/systems/{wms}/managers/{kim_id}", headers=h).status_code == 200


def test_cannot_remove_last_manager(client, as_user):
    h = as_user("jung.cust@example.com")
    crm = _sys_id(client, h, "CRM")
    me = client.get(f"{API}/auth/me", headers=h).json()["user"]["id"]
    for m in client.get(f"{API}/systems/{crm}", headers=h).json()["managers"]:  # 나만 남긴다
        if m["id"] != me:
            assert client.delete(f"{API}/systems/{crm}/managers/{m['id']}", headers=h).status_code == 200
    r = client.delete(f"{API}/systems/{crm}/managers/{me}", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "last_manager"


def test_system_filters(client, as_user):
    h = as_user(HONG)
    assert {s["code"] for s in client.get(f"{API}/systems?mine=true", headers=h).json()} == {"WMS", "CSBOT"}
    assert {s["code"] for s in client.get(f"{API}/systems?kind=AGENT", headers=h).json()} == {"CSBOT", "PURCH", "MKT", "PLAN", "A2X"}
    assert {s["code"] for s in client.get(f"{API}/systems?q=생산", headers=h).json()} >= {"MES", "PLAN"}  # 업무 프로세스로도 찾는다
    assert {s["code"] for s in client.get(f"{API}/systems?q=mes", headers=h).json()} == {"MES"}  # 영문 약어(이름 = 코드)


def test_requires_login(client):
    assert client.get(f"{API}/systems").status_code == 401


# ---------- 서버 ----------


def test_servers_add_list_delete(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    r = client.post(f"{API}/systems/{wms}/servers", headers=h, json={"hostname": "wms-api02", "ip": "10.10.2.22", "port": 8080, "env": "STAGE", "role": "API"})
    assert r.status_code == 201
    assert client.post(f"{API}/systems/{wms}/servers", headers=h, json={"hostname": "wms-api02", "ip": "1.1.1.1", "port": 1}).status_code == 409
    rows = client.get(f"{API}/servers?mine=true&env=STAGE", headers=h).json()
    assert [s["hostname"] for s in rows] == ["wms-api02"]
    assert client.delete(f"{API}/servers/{r.json()['id']}", headers=as_user(KIM)).status_code == 403
    assert client.delete(f"{API}/servers/{r.json()['id']}", headers=h).status_code == 200


def test_update_server(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    a = client.post(f"{API}/systems/{wms}/servers", headers=h, json={"hostname": "wms-api02", "ip": "10.10.2.22", "port": 8080, "env": "STAGE", "role": "API"}).json()
    client.post(f"{API}/systems/{wms}/servers", headers=h, json={"hostname": "wms-api03", "ip": "10.10.2.23", "port": 8080})
    r = client.put(f"{API}/servers/{a['id']}", headers=h, json={"hostname": "wms-api02", "ip": "10.10.2.99", "port": 9090, "env": "PROD", "role": "WAS"})
    assert r.status_code == 200 and (r.json()["ip"], r.json()["port"], r.json()["env"]) == ("10.10.2.99", 9090, "PROD")
    # 같은 시스템의 다른 서버와 호스트명이 겹치면 409, 담당자가 아니면 403
    assert client.put(f"{API}/servers/{a['id']}", headers=h, json={"hostname": "wms-api03", "ip": "1.1.1.1", "port": 1}).status_code == 409
    assert client.put(f"{API}/servers/{a['id']}", headers=as_user(KIM), json={"hostname": "x", "ip": "1.1.1.1", "port": 1}).status_code == 403


def test_update_system_info(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    r = client.patch(f"{API}/systems/{wms}", headers=h, json={"dept": "물류혁신팀", "url": "https://wms.example", "data_level": "CONFIDENTIAL", "description": "수정"})
    assert r.status_code == 200 and (r.json()["dept"], r.json()["data_level"]) == ("물류혁신팀", "CONFIDENTIAL")


def _mcp_body_from(detail):
    return {
        "system_id": detail["system"]["id"], "name": detail["name"], "version": detail["version"], "description": detail["description"],
        "business": detail["business"], "transport": detail["transport"] or "STREAMABLE_HTTP", "endpoint": detail["endpoint"], "auth_type": detail["auth_type"] or "",
        "host_server_id": detail["host_server_id"],
        "tools": [{"name": t["name"], "description": t["description"], "kind": t["kind"], "exposed": t["exposed"]} for t in detail["tools"]],
    }


def test_live_mcp_edit_keeps_tool_rows_and_blocks_removing_requested_tool(client, as_user):
    admin = as_user(ADMIN)
    irp = next(a for a in client.get(f"{API}/assets?type=MCP", headers=admin).json() if a["system"]["code"] == "IRP")
    d = client.get(f"{API}/assets/{irp['id']}", headers=admin).json()
    ids = {t["name"]: t["id"] for t in d["tools"]}
    # 신청 내역이 있는 Tool(search_systems)은 뺄 수 없다
    body = _mcp_body_from(d)
    body["tools"] = [t for t in body["tools"] if t["name"] != "search_systems"]
    r = client.put(f"{API}/assets/{irp['id']}/mcp", headers=admin, json=body)
    assert r.status_code == 422 and r.json().get("code") == "tool_in_use", r.text
    # 설명만 바꾸면 Tool 행(ID)은 그대로, 상태는 재승인 대기
    body = _mcp_body_from(d)
    body["tools"][0]["description"] = "설명 수정"
    r = client.put(f"{API}/assets/{irp['id']}/mcp", headers=admin, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING" and {t["name"]: t["id"] for t in r.json()["tools"]} == ids


def test_server_used_by_mcp_cannot_be_deleted(client, as_user):
    h = as_user(HONG)
    mcp_host = next(s for s in client.get(f"{API}/servers?q=wms-mcp01", headers=h).json())
    r = client.delete(f"{API}/servers/{mcp_host['id']}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "server_in_use"


# ---------- API 등록 · 진행상태 ----------


def test_api_lifecycle(client, as_user):
    h, admin = as_user(HONG), as_user(ADMIN)
    wms = _sys_id(client, h, "WMS")
    r = client.post(f"{API}/assets/api", headers=h, json=api_body(wms))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["status"] == "DRAFT" and a["operation_count"] == 2 and len(a["request_layout"]) == 1 and a["icon"]["name"] == "warehouse"
    aid = a["id"]

    # 저장 상태는 다른 사람에게 안 보인다
    assert client.get(f"{API}/assets/{aid}", headers=as_user(KIM)).status_code == 404
    assert aid not in [x["id"] for x in client.get(f"{API}/assets", headers=as_user(KIM)).json()]

    # 담당자만 제출, admin만 승인 · 운영 전환
    assert client.post(f"{API}/assets/{aid}/submit", headers=as_user(KIM)).status_code == 404
    assert client.post(f"{API}/assets/{aid}/submit", headers=h).json()["status"] == "PENDING"
    assert client.post(f"{API}/assets/{aid}/approve", headers=h).status_code == 403
    assert client.post(f"{API}/assets/{aid}/approve", headers=admin).json()["status"] == "STAGE"
    assert client.post(f"{API}/assets/{aid}/go-live", headers=admin).json()["status"] == "LIVE"
    # 잘못된 전이
    r = client.post(f"{API}/assets/{aid}/approve", headers=admin)
    assert r.status_code == 422 and r.json()["code"] == "invalid_transition"
    # 운영 중 수정 → 재승인(승인 대기). 같은 리소스는 행을 고쳐 쓴다(ID 유지)
    ops = {(o["method"], o["path"]): o["id"] for o in client.get(f"{API}/assets/{aid}", headers=h).json()["operations"]}
    body = api_body(wms, description="설명 수정")
    body["operations"][0]["summary"] = "재고 이력 목록"
    r = client.put(f"{API}/assets/{aid}/api", headers=h, json=body)
    assert r.status_code == 200 and r.json()["status"] == "PENDING" and r.json()["description"] == "설명 수정"
    assert {(o["method"], o["path"]): o["id"] for o in r.json()["operations"]} == ops
    assert r.json()["operations"][0]["summary"] == "재고 이력 목록"
    assert client.put(f"{API}/assets/{aid}/api", headers=as_user(KIM), json=body).status_code in (403, 404)


def test_reject_then_edit_and_resubmit(client, as_user):
    h, admin = as_user(HONG), as_user(ADMIN)
    wms = _sys_id(client, h, "WMS")
    aid = client.post(f"{API}/assets/api", headers=h, json=api_body(wms, submit=True)).json()["id"]
    assert client.post(f"{API}/assets/{aid}/reject", headers=admin, json={"note": "Base URL 확인"}).json()["status"] == "REJECTED"
    r = client.put(f"{API}/assets/{aid}/api", headers=h, json=api_body(wms, name="재고 이력 API v2", submit=True))
    assert r.status_code == 200 and r.json()["status"] == "PENDING" and r.json()["name"] == "재고 이력 API v2"


def test_submit_requires_fields(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    r = client.post(f"{API}/assets/api", headers=h, json=api_body(wms, base_url="", operations=[], submit=True))
    assert r.status_code == 422 and r.json()["code"] == "incomplete"
    assert "Base URL" in r.json()["detail"] and "리소스" in r.json()["detail"]


def test_api_validation(client, as_user):
    h = as_user(HONG)
    wms, csbot = _sys_id(client, h, "WMS"), _sys_id(client, h, "CSBOT")
    dup_ops = api_body(wms, operations=[{"method": "GET", "path": "/a"}, {"method": "GET", "path": "/a"}])
    assert client.post(f"{API}/assets/api", headers=h, json=dup_ops).json()["code"] == "duplicate_operation"
    assert client.post(f"{API}/assets/api", headers=h, json=api_body(wms, name="입출고 API")).json()["code"] == "name_taken"
    assert client.post(f"{API}/assets/api", headers=h, json=api_body(csbot)).json()["code"] == "agent_system"
    erp = _sys_id(client, h, "ERP")
    assert client.post(f"{API}/assets/api", headers=h, json=api_body(erp)).status_code == 403
    assert client.post(f"{API}/assets/api", headers=h, json=api_body(wms, operations=[{"method": "GET", "path": "no-slash"}])).status_code == 422


# ---------- MCP 등록 ----------


def mcp_body(system_id, server_id=None, **kw):
    body = {
        "system_id": system_id,
        "name": "재고 알림 MCP",
        "business": {"name": "재고 알림"},
        "transport": "STREAMABLE_HTTP",
        "endpoint": "https://wms.internal.example/mcp/alerts",
        "auth_type": "OAuth2 Client Credentials",
        "host_server_id": server_id,
        "tools": [{"name": "list_alerts", "kind": "READ"}, {"name": "ack_alert", "kind": "WRITE", "exposed": False}],
    }
    body.update(kw)
    return body


def test_mcp_register_and_hidden_tools(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    srv = next(s["id"] for s in client.get(f"{API}/servers?q=wms-mcp01", headers=h).json())
    r = client.post(f"{API}/assets/mcp", headers=h, json=mcp_body(wms, srv, submit=True))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["source"] == "MCP_DIRECT" and a["status"] == "PENDING" and a["host_server_id"] == srv
    assert a["tool_count"] == 1 and len(a["tools"]) == 2  # 카탈로그 공개는 1개


def test_mcp_validation(client, as_user):
    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    other_srv = next(s["id"] for s in client.get(f"{API}/servers?q=erp-was01", headers=h).json())
    assert client.post(f"{API}/assets/mcp", headers=h, json=mcp_body(wms, other_srv)).json()["code"] == "invalid_server"
    assert client.post(f"{API}/assets/mcp", headers=h, json=mcp_body(wms, endpoint="ftp://x")).json()["code"] == "invalid_endpoint"
    dup = mcp_body(wms, tools=[{"name": "a"}, {"name": "a"}])
    assert client.post(f"{API}/assets/mcp", headers=h, json=dup).json()["code"] == "duplicate_tool"
    no_exposed = mcp_body(wms, tools=[{"name": "a", "exposed": False}], submit=True)
    assert client.post(f"{API}/assets/mcp", headers=h, json=no_exposed).json()["code"] == "incomplete"


# ---------- 카탈로그 · 아이콘 · 감사 ----------


def test_catalog_filters_and_counts(client, as_user):
    h = as_user(KIM)
    rows = client.get(f"{API}/assets?type=MCP", headers=h).json()
    assert len(rows) == 8 and all(r["type"] == "MCP" for r in rows)  # IRP · DCM MCP 포함
    stock = next(r for r in rows if r["name"] == "재고 MCP 서버")
    assert stock["subscriber_count"] == 1 and stock["tool_count"] == 4
    assert {r["name"] for r in client.get(f"{API}/assets?q=공급망", headers=h).json()} == {"발주 관리 API", "공급사 정보 MCP", "수요 예측 API"}
    detail = client.get(f"{API}/assets/{stock['id']}", headers=h).json()
    assert detail["endpoint"].endswith("/mcp") and [t["name"] for t in detail["tools"]][0] == "get_stock"


def test_set_icon(client, as_user):
    h = as_user(HONG)
    stock = next(r for r in client.get(f"{API}/assets?q=재고 MCP", headers=h).json())
    r = client.put(f"{API}/assets/{stock['id']}/icon", headers=h, json={"name": "truck", "color": "#6e4ff6"})
    assert r.status_code == 200 and r.json()["icon"] == {"kind": "PRESET", "name": "truck", "color": "#6e4ff6"}
    assert client.put(f"{API}/assets/{stock['id']}/icon", headers=h, json={"name": "truck", "color": "red"}).status_code == 422
    assert client.put(f"{API}/assets/{stock['id']}/icon", headers=as_user(KIM), json={"name": "truck", "color": "#000000"}).status_code == 403


def test_actions_are_audited(client, as_user, session_factory):
    from src.audit.models import AuditLog

    h = as_user(HONG)
    wms = _sys_id(client, h, "WMS")
    aid = client.post(f"{API}/assets/api", headers=h, json=api_body(wms, submit=True)).json()["id"]
    client.post(f"{API}/assets/{aid}/approve", headers=as_user(ADMIN))
    with session_factory() as s:
        actions = [a.action for a in s.query(AuditLog).filter(AuditLog.target_type == "asset", AuditLog.target_id == str(aid)).order_by(AuditLog.id)]
    assert actions == ["asset.create", "asset.submit", "asset.approve"]
