"""프로세스 자동화 Agent (T3-4): 외부 시스템(MCP)을 읽어 등록 · 구독 양식의 입력란을 채울 값을 제안한다.

읽는 곳: API 등록 · MCP 등록 → 마스터 MCP, 시스템 등록 → IRP(시스템 마스터) + DCM(서버 자산), 서버 등록 → DCM.

모두 코드 규칙이다: 양식 판별 → 시스템 특정(담당 시스템 안에서) → 마스터 조회 → 필드 사전으로 매핑 → 스키마 검증.
**제출하지 않는다**(가드레일 1). form_suggestion만 돌려주고, 사용자가 화면에서 확인 후 직접 저장 · 승인 요청한다.
값이 여러 개로 갈리면 추측하지 않고 선택지(actions: ask)를 돌려준다.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import ValidationError

from src.agents.state import AgentResult
from src.catalog.schemas import ApiAssetIn, McpAssetIn
from src.systems.schemas import ServerIn, SystemIn
from src.knowledge.evidence import keywords
from src.shared import trace
from src.systems.service import system_label
from src.tools.master_client import MasterClient, MasterError

FORM_BY_PAGE = {"publish": "api", "mcp-register": "mcp", "catalog": "subscription", "subscriptions": "subscription", "systems": "system", "servers": "server"}
FORM_PAGE = {"api": "publish", "mcp": "mcp-register", "subscription": "catalog", "system": "systems", "server": "servers", "system_servers": "systems"}
FORM_LABEL = {"api": "API 등록", "mcp": "MCP 등록", "subscription": "시스템 구독 신청", "system": "시스템 등록", "server": "서버 등록",
              "system_servers": "시스템 등록의 서버 정보"}
# 대상(API · MCP)을 고를 때 빼는 말: 양식 · 동작 표현
NOISE = {"api", "mcp", "서버", "등록", "신청", "구독", "사용", "채워", "채우", "채움", "자동", "입력", "작성", "양식", "화면", "대신", "부탁", "자동채움"}


class Portal(Protocol):
    def list_systems(self) -> list[dict[str, Any]]: ...
    def list_my_systems(self) -> list[dict[str, Any]]: ...
    def my_role(self) -> str: ...
    def users_by_email(self, emails: list[str]) -> list[dict[str, Any]]: ...
    def search_catalog(self, q: str | None = None, live_only: bool = True) -> list[dict[str, Any]]: ...
    def get_asset(self, asset_id: int) -> dict[str, Any] | None: ...


def detect_form(message: str, page: str | None) -> str | None:
    t = message.lower()
    if re.search(r"구독|사용\s?신청", t):
        return "subscription"
    if re.search(r"mcp\s?(서버)?\s?(등록|채워|채우|입력)", t):
        return "mcp"
    if re.search(r"api\s?(등록|채워|채우|입력)", t):
        return "api"
    if re.search(r"시스템\s?(등록\s?)?(의\s?)?서버", t):  # 시스템 등록 양식의 서버 정보만
        return "system_servers"
    if re.search(r"서버\s?(등록|추가|채워|채우|입력)", t):
        return "server"
    if re.search(r"시스템\s?(등록|채워|채우|입력)", t):
        return "system"
    return FORM_BY_PAGE.get(page or "")


def mentioned_systems(message: str, systems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """메시지에 코드(단어 단위) 또는 이름이 나온 시스템."""
    t = message.lower()
    return [s for s in systems if re.search(rf"(?<![a-z0-9]){re.escape(s['code'].lower())}(?![a-z0-9])", t) or s["name"].lower() in t]


def _terms(message: str, exclude: list[dict[str, Any]]) -> list[str]:
    drop = set(NOISE)
    for s in exclude:
        drop |= {s["code"].lower(), *keywords(s["name"])}
    return [w for w in keywords(message) if w not in drop]


def _best(items: list[dict[str, Any]], terms: list[str], *fields: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """점수(일치 단어 수)가 가장 높은 하나. 갈리면 (None, 후보들)."""
    if not items:
        return None, []
    scored = [(sum(w in " ".join(str(it.get(f, "")) for f in fields).lower() for w in terms), it) for it in items]
    top = max(sc for sc, _ in scored)
    cands = [it for sc, it in scored if sc == top]
    if len(cands) == 1 and (top > 0 or len(items) == 1):
        return cands[0], []
    return None, cands if top > 0 else items


def _ask(label: str, message: str) -> dict[str, str]:
    return {"type": "ask", "label": label, "message": message}


def _open(form: str) -> dict[str, str]:
    return {"type": "open", "page": FORM_PAGE[form], "label": f"{FORM_LABEL[form]} 화면에서 확인"}


def _validate(model, values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """양식 스키마로 검증. 실패한 항목은 비우고 메모로 알린다(잘못된 값을 채우지 않음)."""
    try:
        return model.model_validate(values).model_dump(mode="json", exclude={"submit", "icon"}), []
    except ValidationError as e:
        bad = {str(err["loc"][0]) for err in e.errors()}
        kept = {k: v for k, v in values.items() if k not in bad}
        notes = [f"마스터 값이 양식 규칙에 맞지 않아 비워 둔 항목: {', '.join(sorted(bad))}"]
        try:
            return model.model_validate(kept).model_dump(mode="json", exclude={"submit", "icon"}), notes
        except ValidationError:
            return kept, notes


def _done(form: str, values: dict, source: dict, filled: list[str], notes: list[str], tools: list[str], head: str) -> AgentResult:
    trace.step(trace.actor(), "양식 값 매핑 · 스키마 검증(코드)", f"{FORM_LABEL[form]}: {', '.join(filled)}" + (f" · 메모 {len(notes)}건" if notes else ""))
    lines = [head, f"채운 항목: {', '.join(filled)}."] + [f"※ {n}" for n in notes]
    lines.append("제출은 하지 않았습니다. 화면에서 값을 확인한 뒤 직접 저장 · 승인 요청해 주세요.")
    return AgentResult(
        answer="\n".join(lines),
        sources=[source],
        form_suggestion={"form": form, "values": values, "source": source, "notes": notes},
        actions=[_open(form)],
        used_tools=tools,
    )


async def _owned_system(form: str, message: str, portal: Portal, master: MasterClient | None = None) -> tuple[dict | None, AgentResult | None]:
    """등록 양식: 내가 담당하는 업무 시스템 중에서만 고른다(화면과 같이 Agent 시스템은 제외).
    시스템을 말하지 않았으면 마스터에서 대상(API · MCP)이 있는 시스템을 찾는다."""
    mine = [s for s in portal.list_my_systems() if s.get("kind", "BUSINESS") == "BUSINESS"]
    if not mine:
        return None, AgentResult(
            answer=f"{FORM_LABEL[form]}은(는) 업무 시스템의 담당자만 할 수 있습니다. 기준정보 › 시스템에서 담당 시스템을 등록하거나, 기존 담당자에게 담당자 추가를 요청해 주세요.",
            actions=[{"type": "open", "page": "systems", "label": "시스템 화면 열기"}],
            used_tools=["portal.list_my_systems"],
        )
    named = mentioned_systems(message, mine)
    if len(named) == 1:
        return named[0], None
    if len(mine) == 1 and not named:
        return mine[0], None
    choices = named or mine
    terms = _terms(message, choices)
    if terms and master is not None:  # 예: '재고 이력 API 채워줘' → 마스터에 그 API가 있는 담당 시스템이 하나면 그것
        tool, fields = ("search_apis", ("api_code", "name", "business_name")) if form == "api" else ("get_mcp_server", ("name", "description"))
        hits = []
        for sys_ in choices:
            items = await master.call(tool, system_code=sys_["code"])
            if any(any(w in " ".join(str(it.get(f, "")) for f in fields).lower() for w in terms) for it in items):
                hits.append(sys_)
        if len(hits) == 1:
            return hits[0], None
    return None, AgentResult(
        answer=f"어느 시스템의 {FORM_LABEL[form]}을(를) 채울까요? 담당 시스템 중에서 골라 주세요.",
        actions=[_ask(system_label(s["code"], s["name"]), f"{s['code']} {FORM_LABEL[form]} 채워줘") for s in choices],
        used_tools=["portal.list_my_systems"],
    )


async def _fill_api(message: str, portal: Portal, master: MasterClient) -> AgentResult:
    system, stop = await _owned_system("api", message, portal, master)
    if stop:
        return stop
    tools = ["portal.list_my_systems", "master.search_apis"]
    apis = await master.call("search_apis", system_code=system["code"])
    if not apis:
        return AgentResult(
            answer=f"API 마스터에 {system['code']} 시스템의 API가 없습니다. 입력란을 직접 채워 주세요(Swagger · 샘플 JSON 가져오기도 쓸 수 있습니다).",
            form_suggestion={"form": "api", "values": {"system_id": system["id"]}, "source": {"type": "portal", "system": system["code"]}, "notes": []},
            actions=[_open("api")], used_tools=tools,
        )
    pick, cands = _best(apis, _terms(message, [system]), "api_code", "name", "business_name")
    if pick is None:
        return AgentResult(
            answer=f"{system['code']} 시스템의 API 마스터에 후보가 {len(cands)}개 있습니다. 어떤 API를 등록할까요?",
            actions=[_ask(f"{a['name']} ({a['api_code']})", f"{system['code']} {a['name']} API 등록 채워줘") for a in cands],
            used_tools=tools,
        )
    a = await master.call("get_api", api_code=pick["api_code"])
    tools.append("master.get_api")
    raw = {
        "system_id": system["id"], "name": a["name"], "version": a.get("version", "1.0.0"), "description": a.get("description", ""),
        "business": a.get("business", {}), "direction": a.get("direction", "SEND"), "base_url": a.get("base_url", ""),
        "auth_type": a.get("auth_type", ""), "content_type": a.get("content_type", "application/json"), "timeout_ms": a.get("timeout_ms", 5000),
        "operations": a.get("operations", []), "request_layout": a.get("request_layout", []), "response_layout": a.get("response_layout", []),
    }
    values, notes = _validate(ApiAssetIn, raw)
    if not values.get("operations"):
        notes.append("마스터에 리소스(메소드 · 경로)가 없어 직접 입력해야 합니다.")
    filled = ["시스템 정보", "기본정보", "업무정보", "API 타입"]
    filled += [f"리소스 {len(values.get('operations', []))}건"] if values.get("operations") else []
    n_layout = len(values.get("request_layout", [])) + len(values.get("response_layout", []))
    filled += [f"레이아웃 {n_layout}건"] if n_layout else []
    source = {"type": "master", "tool": "get_api", "key": a["api_code"], "label": f"API 마스터 › {a['name']}"}
    return _done("api", values, source, filled, notes, tools, f"API 마스터의 '{a['name']}'({a['api_code']}) 정보로 {system['code']} API 등록 양식을 채웠습니다.")


async def _fill_mcp(message: str, portal: Portal, master: MasterClient) -> AgentResult:
    system, stop = await _owned_system("mcp", message, portal, master)
    if stop:
        return stop
    tools = ["portal.list_my_systems", "master.get_mcp_server"]
    servers = await master.call("get_mcp_server", system_code=system["code"])
    if not servers:
        return AgentResult(
            answer=f"MCP 서버 마스터에 {system['code']} 시스템의 MCP 서버가 없습니다. 연결 정보와 Tool을 직접 입력해 주세요.",
            form_suggestion={"form": "mcp", "values": {"system_id": system["id"]}, "source": {"type": "portal", "system": system["code"]}, "notes": []},
            actions=[_open("mcp")], used_tools=tools,
        )
    pick, cands = _best(servers, _terms(message, [system]), "name", "description")
    if pick is None:
        return AgentResult(
            answer=f"{system['code']} 시스템의 MCP 서버 마스터에 후보가 {len(cands)}개 있습니다. 어떤 서버를 등록할까요?",
            actions=[_ask(m["name"], f"{system['code']} {m['name']} 등록 채워줘") for m in cands],
            used_tools=tools,
        )
    notes: list[str] = []
    host = next((v for v in system.get("servers", []) if v["hostname"] == pick.get("host")), None)
    if pick.get("host") and host is None:
        notes.append(f"호스트 서버 {pick['host']}가 포탈 서버 목록에 없어 비워 두었습니다(기준정보 › 서버에서 추가).")
    raw = {
        "system_id": system["id"], "name": pick["name"], "description": pick.get("description", ""), "business": pick.get("business", {}),
        "transport": pick.get("transport", "STREAMABLE_HTTP"), "endpoint": pick.get("endpoint", ""), "auth_type": pick.get("auth_type", ""),
        "host_server_id": host["id"] if host else None, "protocol_version": pick.get("protocol_version", "2025-06-18"),
        "tools": [{"name": t["name"], "description": t.get("description", ""), "kind": t.get("kind", "READ"), "exposed": True} for t in pick.get("tools", [])],
    }
    values, more = _validate(McpAssetIn, raw)
    notes += more
    writes = [t["name"] for t in values.get("tools", []) if t.get("kind") == "WRITE"]
    if writes:
        notes.append(f"변경 Tool이 있습니다({', '.join(writes)}). 공개 여부를 확인해 주세요.")
    filled = ["시스템 정보", "기본정보", "업무정보", "연결 정보", f"Tool {len(values.get('tools', []))}개"]
    source = {"type": "master", "tool": "get_mcp_server", "key": f"{system['code']}/{pick['name']}", "label": f"MCP 서버 마스터 › {pick['name']}"}
    return _done("mcp", values, source, filled, notes, tools, f"MCP 서버 마스터의 '{pick['name']}' 정보로 {system['code']} MCP 등록 양식을 채웠습니다.")


async def _fill_subscription(message: str, portal: Portal, asset_id: int | None) -> AgentResult:
    tools = ["portal.list_my_systems"]
    mine = portal.list_my_systems()
    # 메시지가 대상을 하나로 특정하면 그것을 쓴다(화면에서 고른 자산보다 우선)
    named = None
    if terms0 := _terms(message, mine):
        named, _ = _best(portal.search_catalog(None), terms0, "name", "system_code", "system_name")
        tools.append("portal.search_catalog")
    if named is not None:
        asset = named
    elif asset_id:
        asset = portal.get_asset(asset_id)
        tools.append("portal.get_asset")
        if asset is None or asset["status"] != "LIVE":
            return AgentResult(answer="선택한 API · MCP는 운영 상태가 아니어서 구독 신청할 수 없습니다.", used_tools=tools)
    else:
        terms = _terms(message, mine)
        live = portal.search_catalog(None)
        tools.append("portal.search_catalog")
        asset, cands = _best(live, terms, "name", "system_code", "system_name") if terms else (None, [])
        if asset is None:
            if not cands:
                return AgentResult(
                    answer="어떤 API · MCP를 구독할지 알려 주세요. 카탈로그에서 항목을 고른 뒤 다시 요청해도 됩니다.",
                    actions=[{"type": "open", "page": "catalog", "label": "카탈로그 열기"}], used_tools=tools,
                )
            return AgentResult(
                answer=f"구독할 대상 후보가 {len(cands)}개 있습니다. 어떤 것을 신청할까요?",
                actions=[_ask(f"{c['system_code']} {c['name']}", f"{c['system_code']} {c['name']} 구독 신청 채워줘") for c in cands[:6]],
                used_tools=tools,
            )
    clients = [s for s in mine if s["id"] != asset["system_id"]]  # 자기 시스템 자산은 구독하지 않는다
    if not clients:
        return AgentResult(
            answer="시스템 구독은 클라이언트 시스템의 담당자가 신청합니다. 담당 시스템이 없어 신청 양식을 채울 수 없습니다. 담당자에게 요청하거나 담당자로 추가해 달라고 요청해 주세요.",
            used_tools=tools,
        )
    named = mentioned_systems(message, clients)
    client = named[0] if len(named) == 1 else clients[0] if len(clients) == 1 else None
    if client is None:
        return AgentResult(
            answer=f"어느 시스템으로 '{asset['name']}'을(를) 구독할까요?",
            actions=[_ask(system_label(s["code"], s["name"]), f"{s['code']}에서 {asset['system_code']} {asset['name']} 구독 신청 채워줘") for s in (named or clients)],
            used_tools=tools,
        )
    values = {"client_system_id": client["id"], "asset_id": asset["id"], "purpose": f"{client['name']}에서 {asset['system_name']}의 {asset['name']} 연계 사용"}
    notes = ["신청 목적은 예시 문구입니다. 실제 사용 목적에 맞게 고쳐 주세요."]
    if asset["type"] == "MCP":
        notes.append("구독이 승인되면 사용자별로 필요한 Tool을 따로 신청해야 합니다.")
    source = {"type": "portal", "tool": "search_catalog", "key": str(asset["id"]), "label": f"카탈로그 › {asset['system_code']} {asset['name']}"}
    return _done("subscription", values, source, ["클라이언트 시스템", "대상 API · MCP", "신청 목적(예시)"], notes, tools,
                 f"{client['code']} 시스템이 '{asset['name']}'({asset['system_code']})을(를) 구독하는 신청 양식을 채웠습니다.")


def _needs_system(form: str, portal: Portal) -> AgentResult | None:
    """서버 추가는 담당 시스템이 있어야 한다(화면과 같은 기준). 시스템 등록은 누구나 할 수 있다."""
    if portal.my_role() == "USER":
        return AgentResult(
            answer=f"{FORM_LABEL[form]}은(는) 담당 시스템이 있어야 할 수 있습니다. 먼저 시스템을 등록하거나 시스템 담당자에게 담당자 추가를 요청하세요.",
            actions=[{"type": "open", "page": "systems", "label": "시스템 화면 열기"}],
            used_tools=["portal.my_role"],
        )
    return None


async def _fill_system(message: str, portal: Portal, irp: MasterClient, dcm: MasterClient) -> AgentResult:
    """IRP에서 아직 포탈에 없는 시스템을 찾아 기본정보 · 담당자, DCM에서 그 시스템의 서버를 읽어 시스템 등록 양식을 채운다."""
    tools = ["portal.my_role", "portal.list_systems", "irp.search_systems"]
    registered = {s["code"] for s in portal.list_systems()}
    found = await irp.call("search_systems")
    named = mentioned_systems(message, [{"code": x["system_code"], "name": x["name"]} for x in found])
    if not named:
        pick, _ = _best([{**x, "code": x["system_code"]} for x in found], _terms(message, []), "system_code", "name", "dept", "process", "description")
        named = [pick] if pick else []
    new = [x for x in found if x["system_code"] not in registered]
    if len(named) != 1:
        if not new:
            return AgentResult(answer="IRP의 시스템이 모두 포탈에 등록되어 있습니다.", used_tools=tools)
        return AgentResult(
            answer=f"IRP에 있고 아직 포탈에 없는 시스템이 {len(new)}개 있습니다. 어떤 시스템을 등록할까요?",
            actions=[_ask(f"{x['system_code']} · {x['description'][:18]}", f"{x['system_code']} 시스템 등록 채워줘") for x in new[:8]],
            used_tools=tools,
        )
    code = named[0]["code"]
    if code in registered:
        return AgentResult(answer=f"{code}는 이미 포탈에 등록된 시스템입니다. 시스템 화면에서 확인하세요.",
                           actions=[{"type": "open", "page": "systems", "label": "시스템 화면 열기"}], used_tools=tools)
    d = await irp.call("get_system", system_code=code)
    servers = await dcm.call("search_servers", system_code=code)
    tools += ["irp.get_system", "dcm.search_servers"]

    notes: list[str] = []
    irp_mgrs = d.get("managers", [])
    members = portal.users_by_email([m["email"] for m in irp_mgrs])
    tools.append("portal.users_by_email")
    member_emails = {u["email"] for u in members}
    missing = [m["name"] for m in irp_mgrs if m["email"].lower() not in member_emails]
    if missing:
        notes.append(f"IRP 담당자 중 포탈 미가입자는 빼 두었습니다: {', '.join(missing)}(가입 후 담당자 추가)")
    raw = {
        "code": code, "name": d.get("name") or code, "kind": d.get("kind", "BUSINESS"), "process": d.get("process", ""), "dept": d.get("dept", ""),
        "url": d.get("url", ""), "data_level": d.get("data_level", "INTERNAL"), "description": d.get("description", ""),
        "manager_emails": [u["email"] for u in members],
        "servers": [{"hostname": sv["hostname"], "ip": sv["ip"], "port": sv["port"], "env": sv["env"], "role": sv.get("role", "")} for sv in servers],
    }
    values, more = _validate(SystemIn, raw)
    notes += more
    values["managers"] = members  # 화면의 담당자 칩 표시용(이름 · 이메일)
    filled = ["기본정보", f"담당자 {len(members)}명", f"서버 {len(values.get('servers', []))}대"]
    source = {"type": "master", "tool": "get_system", "key": code, "label": f"IRP 시스템 마스터 · DCM 서버 자산 › {code}"}
    return _done("system", values, source, filled, notes, tools, f"IRP · DCM 정보로 {code} 시스템 등록 양식을 채웠습니다.")


CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9_-]{1,29})(?![A-Za-z0-9])")
NOT_CODE = {"API", "MCP", "A2X", "IRP", "DCM", "AI"}


async def _fill_system_servers(message: str, portal: Portal, dcm: MasterClient) -> AgentResult:
    """시스템 등록 양식의 서버 정보: 양식에 입력한 시스템 코드로 DCM에서 서버를 읽어 서버 행만 제안한다(다른 입력값은 건드리지 않음)."""
    codes = [c for c in CODE_RE.findall(message) if c not in NOT_CODE] or [c for c in CODE_RE.findall(message.upper()) if c not in NOT_CODE and len(c) <= 10]
    if not codes:
        return AgentResult(answer="시스템 등록 양식에 시스템 코드를 먼저 입력해 주세요. 그 코드로 DCM에서 서버를 찾아 채웁니다.", used_tools=[])
    code = codes[0].upper()
    tools = ["portal.my_role", "portal.list_systems", "dcm.search_servers"]
    if code in {x["code"] for x in portal.list_systems()}:
        return AgentResult(answer=f"{code}는 이미 포탈에 등록된 시스템입니다. 서버는 기준정보 › 서버에서 추가하세요.",
                           actions=[{"type": "open", "page": "servers", "label": "서버 화면 열기"}], used_tools=tools)
    servers = await dcm.call("search_servers", system_code=code)
    if not servers:
        return AgentResult(answer=f"DCM에 {code} 시스템의 서버가 없습니다. 서버 정보를 직접 입력해 주세요.", used_tools=tools)
    rows, notes = [], []
    for sv in servers:
        v, more = _validate(ServerIn, {k: sv[k] for k in ("hostname", "ip", "port", "env", "role")})
        if more:
            notes.append(f"{sv['hostname']}: {more[0]}")
        rows.append(v)
    values = {"code": code, "servers": rows}
    source = {"type": "master", "tool": "search_servers", "key": code, "label": f"DCM 서버 자산 › {code}"}
    envs = ", ".join(sorted({r.get("env", "") for r in rows}))
    return _done("system_servers", values, source, [f"서버 {len(rows)}대({envs})"], notes, tools,
                 f"DCM에서 {code} 시스템의 서버 {len(rows)}대를 찾았습니다. 시스템 등록 양식의 서버 정보에 추가합니다.")


async def _fill_server(message: str, portal: Portal, dcm: MasterClient) -> AgentResult:
    """DCM에서 내 시스템의 서버 중 아직 포탈에 없는 것을 찾아 서버 등록 양식을 채운다."""
    if stop := _needs_system("server", portal):
        return stop
    tools = ["portal.my_role", "portal.list_my_systems"]
    cands = portal.list_my_systems()
    if not cands and portal.my_role() == "ADMIN":
        cands = portal.list_systems()
        tools.append("portal.list_systems")
    if not cands:
        return AgentResult(answer="서버를 등록할 수 있는 담당 시스템이 없습니다.", used_tools=tools)
    named = mentioned_systems(message, cands)
    hostname = re.search(r"\b([a-z][a-z0-9]*-[a-z0-9-]+)\b", message.lower())
    if len(named) != 1 and hostname:  # 호스트명으로 시스템을 찾는다
        hit = await dcm.call("search_servers", query=hostname.group(1))
        tools.append("dcm.search_servers")
        named = [s for s in cands if any(h["system_code"] == s["code"] for h in hit)][:1] or named
    system = named[0] if len(named) == 1 else cands[0] if len(cands) == 1 else None
    if system is None:
        return AgentResult(
            answer="어느 시스템의 서버를 등록할까요?",
            actions=[_ask(system_label(s["code"], s["name"]), f"{s['code']} 서버 등록 채워줘") for s in cands[:8]],
            used_tools=tools,
        )
    servers = await dcm.call("search_servers", system_code=system["code"])
    tools.append("dcm.search_servers")
    have = {v["hostname"] for v in system.get("servers", [])}
    new = [sv for sv in servers if sv["hostname"] not in have]
    if not new:
        return AgentResult(answer=f"DCM에 있는 {system['code']} 서버는 모두 포탈에 등록되어 있습니다.", used_tools=tools)
    pick = next((sv for sv in new if hostname and sv["hostname"] == hostname.group(1)), None) or (new[0] if len(new) == 1 else None)
    if pick is None:
        return AgentResult(
            answer=f"DCM에 {system['code']} 서버 중 아직 포탈에 없는 것이 {len(new)}대 있습니다. 어떤 서버를 등록할까요?",
            actions=[_ask(f"{sv['hostname']} ({sv['env']} · {sv['role']} · {sv['ip']})", f"{system['code']} {sv['hostname']} 서버 등록 채워줘") for sv in new[:8]],
            used_tools=tools,
        )
    values, notes = _validate(ServerIn, {k: pick[k] for k in ("hostname", "ip", "port", "env", "role")})
    values["system_id"] = system["id"]
    source = {"type": "master", "tool": "search_servers", "key": pick["hostname"], "label": f"DCM 서버 자산 › {pick['hostname']}"}
    return _done("server", values, source, ["시스템", "호스트명 · IP · 포트 · 환경 · 용도"], notes, tools,
                 f"DCM 정보로 {system['code']} 시스템의 서버 {pick['hostname']} 등록 양식을 채웠습니다.")


async def run(message: str, portal: Portal, master: MasterClient | None = None, page: str | None = None, asset_id: int | None = None,
              irp: MasterClient | None = None, dcm: MasterClient | None = None) -> AgentResult:
    form = detect_form(message, page)
    trace.step(trace.actor(), "양식 판별(코드)", FORM_LABEL[form] if form else "판별 못 함 → 되묻기", ok=form is not None)
    if form is None:
        return AgentResult(
            answer="어떤 양식을 채울까요?",
            actions=[_ask(FORM_LABEL[f], f"{FORM_LABEL[f]} 채워줘") for f in ("api", "mcp", "subscription", "system", "server")],
        )
    try:
        if form == "api":
            return await _fill_api(message, portal, master or MasterClient())
        if form == "mcp":
            return await _fill_mcp(message, portal, master or MasterClient())
        if form == "system":
            return await _fill_system(message, portal, irp or MasterClient.irp(), dcm or MasterClient.dcm())
        if form == "server":
            return await _fill_server(message, portal, dcm or MasterClient.dcm())
        if form == "system_servers":
            return await _fill_system_servers(message, portal, dcm or MasterClient.dcm())
        return await _fill_subscription(message, portal, asset_id)
    except MasterError as e:
        if "권한" in str(e) or "구독" in str(e):  # A2X 중계가 막은 경우: 거버넌스 안내
            apply = (
                {"type": "request", "asset_id": str(e.asset_id), "label": "Tool 사용 신청"}
                if e.asset_id else {"type": "open", "page": "catalog", "label": "카탈로그에서 Tool 신청"}
            )
            return AgentResult(
                answer=f"A2X가 외부 시스템 MCP 호출을 막았습니다: {e}\n해당 MCP의 Tool 사용을 신청하거나(카탈로그 › 사용 신청), 담당자에게 구독 승인을 요청하세요.",
                actions=[apply, _open(form)], used_tools=["master"],
            )
        return AgentResult(answer=f"외부 시스템 MCP를 읽지 못해 자동 채움을 할 수 없습니다({e}). 입력란을 직접 채워 주세요.", actions=[_open(form)], used_tools=["master"])
