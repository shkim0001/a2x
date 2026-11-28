"""인스턴스 모니터링: A2X 구성요소가 정상인지 점검한다(판정은 Python 규칙, LLM 없음).

구성요소 묶음
- 포탈(Control plane): 웹 프런트엔드 · 포탈 API(WAS) · DB · 인증/세션 · 감사 로그
- A2X Agent: LLM · 벡터 DB · 임베딩 모델 · 컨설팅 문서 색인 · Agent 대화
- MCP 권한 Gateway: 권한 판정 정책 DB · 집행 설정 · 최근 권한 거부
- MCP · API Gateway(Data plane): A2X MCP 런타임(8100) · 최근 1시간 트래픽 · WSO2(3차 예정)
- MCP 서버(서버 · 컨테이너별): 운영 · 스테이지 MCP 서버의 연결 상태와 최근 호출 오류율
- 외부 연계 MCP: 마스터 · IRP · DCM
- 운영 데이터: 호출 로그 수집 · 디스크 · 저장소 크기

상태: ok(정상) · warn(주의) · down(비정상) · off(미설정 · 점검 제외). 묶음 · 전체 상태는 가장 나쁜 상태.
네트워크 점검은 동시에, 짧은 시간 제한으로 하고 결과는 잠깐 캐시한다(새로고침이 몰려도 대상 서버를 두드리지 않게).
"""

from __future__ import annotations

import asyncio
import functools
import os
import platform
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from src.audit.models import AuditLog
from src.auth.models import AuthSession
from src.catalog.models import Asset, AssetSource, AssetStatus, AssetType
from src.knowledge.models import ConsultDoc, DocStatus
from src.monitoring.models import CallLog
from src.shared.config import ROOT_DIR, settings

STARTED_AT = time.time()
PROBE_TIMEOUT = 2.0
CACHE_SECONDS = 10
# 판정 기준
ERR_WARN, ERR_DOWN = 5.0, 20.0  # 오류율(%)
SLOW_WARN_MS = 1000  # 점검 응답시간
P95_WARN_MS = 3000  # 최근 호출 p95
DISK_WARN, DISK_DOWN = 10.0, 5.0  # 남은 디스크(%)
LOG_STALE_HOURS = 24  # 호출 로그가 이보다 오래 안 쌓이면 주의
SAMPLE_HOSTS = (".example", ".test", ".invalid")  # 예약된 예시 도메인: 샘플 주소라 실제 연결 점검 제외

RANK = {"ok": 0, "off": 1, "warn": 2, "down": 3}


@dataclass
class Component:
    key: str
    name: str
    status: str
    detail: str
    kind: str = ""  # 표시용 분류(WAS · DB · 컨테이너 등)
    latency_ms: int | None = None
    endpoint: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Group:
    key: str
    label: str
    desc: str
    components: list[Component]

    @property
    def status(self) -> str:
        return worst(c.status for c in self.components)


def worst(statuses) -> str:
    """가장 나쁜 상태. off(미설정 · 점검 제외)는 정상으로 치고, 모두 off일 때만 off."""
    statuses = list(statuses)
    if statuses and all(s == "off" for s in statuses):
        return "off"
    out = "ok"
    for s in statuses:
        if s != "off" and RANK[s] > RANK[out]:
            out = s
    return out


def _is_sample(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith(SAMPLE_HOSTS)


def _loopback(url: str) -> str:
    # Windows에서 localhost는 IPv6를 먼저 시도해 1초가량 늦어진다
    return url.replace("://localhost", "://127.0.0.1")


MCP_PING = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
MCP_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


async def _once(client: httpx.AsyncClient, url: str, mcp: bool, timeout: httpx.Timeout) -> int:
    # MCP 엔드포인트에 GET을 보내면 이벤트 스트림이 열려 끝나지 않으므로 ping(JSON-RPC)을 보내고 응답 헤더만 본다
    if mcp:
        async with client.stream("POST", url, json=MCP_PING, headers=MCP_HEADERS, timeout=timeout) as r:
            return r.status_code
    async with client.stream("GET", url, timeout=timeout) as r:
        return r.status_code


async def probe(client: httpx.AsyncClient, url: str, mcp: bool = False, want_json: bool = False) -> tuple[bool, int | None, int | None, Any, str]:
    """HTTP로 닿는지 본다(어떤 응답 코드든 서버가 응답하면 '살아 있음'). → (닿음, ms, 상태 코드, JSON, 오류)
    127.0.0.1로 먼저 시도하고(Windows localhost 지연 회피), 연결이 안 되면 원래 주소로 다시 시도한다(IPv6로만 듣는 서버, 예: Vite)."""
    last_err = ""
    for target in dict.fromkeys([_loopback(url), url]):
        t0 = time.perf_counter()
        # 127.0.0.1 시도는 연결만 짧게(Windows는 거부된 연결도 2초가량 걸린다)
        timeout = httpx.Timeout(PROBE_TIMEOUT, connect=0.6) if target != url else httpx.Timeout(PROBE_TIMEOUT)
        try:
            if want_json:
                r = await client.get(target, timeout=timeout)
                ms = round((time.perf_counter() - t0) * 1000)
                try:
                    body = r.json()
                except ValueError:
                    body = None
                return True, ms, r.status_code, body, ""
            code = await _once(client, target, mcp, timeout)
            return True, round((time.perf_counter() - t0) * 1000), code, None, ""
        except httpx.TimeoutException:
            last_err = f"{PROBE_TIMEOUT:.0f}초 안에 응답 없음"
        except httpx.HTTPError as e:
            last_err = f"연결 실패({type(e).__name__})"
    return False, None, None, None, last_err


def _reach(key: str, name: str, url: str, res, kind: str, ok_detail: str = "응답함") -> Component:
    reached, ms, code, _body, err = res
    if not reached:
        return Component(key, name, "down", err, kind, None, url)
    status = "warn" if ms and ms > SLOW_WARN_MS else "ok"
    return Component(key, name, status, f"{ok_detail} · HTTP {code}" + (" · 느림" if status == "warn" else ""), kind, ms, url)


def _fmt_uptime(sec: float) -> str:
    sec = int(sec)
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    return f"{d}일 {h}시간" if d else f"{h}시간 {m}분" if h else f"{m}분"


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}MB"


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _ago(dt: datetime | None, now: datetime) -> str:
    if dt is None:
        return "기록 없음"
    s = (now - _utc(dt)).total_seconds()
    return "방금" if s < 60 else f"{int(s // 60)}분 전" if s < 3600 else f"{int(s // 3600)}시간 전" if s < 86400 else f"{int(s // 86400)}일 전"


def _traffic(rows: list[CallLog]) -> dict[str, Any]:
    n = len(rows)
    fails = sum(not r.success for r in rows)
    durs = sorted(r.duration_ms for r in rows)
    p95 = durs[min(len(durs) - 1, int(len(durs) * 0.95))] if durs else 0
    return {"calls": n, "errors": fails, "error_rate": round(fails / n * 100, 2) if n else 0.0, "p95_ms": p95,
            "denied": sum(r.return_code == "403" for r in rows), "server_errors": sum(r.return_code.startswith("5") for r in rows)}


def _traffic_status(t: dict[str, Any]) -> str:
    if t["calls"] == 0:
        return "ok"
    if t["error_rate"] >= ERR_DOWN:
        return "down"
    if t["error_rate"] >= ERR_WARN or t["p95_ms"] >= P95_WARN_MS:
        return "warn"
    return "ok"


# ---------------- 묶음별 점검 ----------------


def _portal(db: Session, now: datetime, frontend) -> Group:
    comps = [Component("portal-api", "포탈 API (WAS)", "ok",
                       f"FastAPI · Python {platform.python_version()} · 가동 {_fmt_uptime(time.time() - STARTED_AT)} · PID {os.getpid()}", "WAS",
                       metrics={"env": settings.APP_ENV})]
    comps.append(_reach("frontend", "웹 프런트엔드", settings.FRONTEND_URL, frontend, "Web", "포탈 화면 응답"))

    # DB: 응답시간 · 방언 · 마이그레이션 버전
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        ms = round((time.perf_counter() - t0) * 1000)
        dialect = db.get_bind().dialect.name
        try:
            current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # noqa: BLE001 — 마이그레이션 표가 없는 DB(테스트 메모리 DB 등)
            current = None
        head = _alembic_head()
        size = ""
        if dialect == "sqlite":
            db_path = ROOT_DIR / settings.DATABASE_URL.split("///", 1)[-1].lstrip("./")
            size = f" · {_mb(_dir_size(db_path))}" if db_path.exists() else ""
        if current and head and current != head:
            comps.append(Component("db", "DB", "warn", f"{dialect} · 마이그레이션 필요(현재 {current} → 최신 {head})", "DB", ms))
        else:
            status = "warn" if ms > SLOW_WARN_MS else "ok"
            comps.append(Component("db", "DB", status, f"{dialect} · 스키마 {current or '-'}{size}", "DB", ms))
    except Exception as e:  # noqa: BLE001
        comps.append(Component("db", "DB", "down", f"조회 실패: {type(e).__name__}", "DB"))

    active = db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.expires_at > now.replace(tzinfo=None))) or 0
    google = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    comps.append(Component("auth", "인증 · 세션", "ok", f"활성 세션 {active}개 · 자체 로그인 · Google 로그인 {'사용' if google else '미설정'}", "Auth",
                           metrics={"sessions": active}))
    last_audit = db.scalar(select(func.max(AuditLog.created_at)))
    comps.append(Component("audit", "감사 로그", "ok", f"마지막 기록 {_ago(last_audit, now)}", "Log"))
    return Group("portal", "포탈 (Control plane)", "사용자 화면 · 포탈 API · 기준정보 DB", comps)


@functools.lru_cache(maxsize=1)
def _alembic_head() -> str | None:
    """최신 마이그레이션 버전(파일에서 한 번만 읽는다)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ROOT_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # noqa: BLE001
        return None


def _agent(db: Session, now: datetime) -> Group:
    from src.knowledge import store as kstore
    from src.shared.llm import has_credentials

    comps = []
    if has_credentials():
        comps.append(Component("llm", "LLM (Claude API)", "ok", f"기본 {settings.ANTHROPIC_DEFAULT_MODEL} · 대체 {settings.ANTHROPIC_FALLBACK_MODEL}", "LLM"))
    else:
        comps.append(Component("llm", "LLM (Claude API)", "off", "API 키 미설정 — Agent는 규칙 기반으로 답합니다", "LLM"))

    st = kstore._store  # 미리 불러오기 전이면 None(여기서 불러오지 않는다: 20초대 import)
    if st is None:
        comps.append(Component("vector", "벡터 DB (ChromaDB)", "warn", "준비 중 — 서버 시작 후 미리 불러오는 중이거나 아직 검색 전", "VectorDB"))
        comps.append(Component("embedding", "임베딩 모델", "warn", f"{settings.EMBEDDING_MODEL} · 아직 불러오지 않음", "Model"))
    else:
        try:
            n = st.count()
            comps.append(Component("vector", "벡터 DB (ChromaDB)", "ok" if n else "warn", f"청크 {n}개" + ("" if n else " — 색인된 문서 없음"), "VectorDB",
                                   metrics={"chunks": n}))
        except Exception as e:  # noqa: BLE001
            comps.append(Component("vector", "벡터 DB (ChromaDB)", "down", f"조회 실패: {type(e).__name__}", "VectorDB"))
        loaded = getattr(st.embedder, "_model", True) is not None  # 테스트용 해시 임베딩은 항상 준비됨
        comps.append(Component("embedding", "임베딩 모델", "ok" if loaded else "warn",
                               f"{settings.EMBEDDING_MODEL} · {'메모리에 올라감' if loaded else '불러오는 중'}", "Model"))

    counts = dict(db.execute(select(ConsultDoc.status, func.count()).group_by(ConsultDoc.status)).all())
    failed, indexing, done = counts.get(DocStatus.FAILED, 0), counts.get(DocStatus.INDEXING, 0), counts.get(DocStatus.INDEXED, 0)
    status = "warn" if failed or indexing else "ok"
    comps.append(Component("docs", "컨설팅 문서 색인", status, f"색인 {done}건" + (f" · 실패 {failed}건" if failed else "") + (f" · 진행 중 {indexing}건" if indexing else ""), "RAG"))

    since = (now - timedelta(hours=24)).replace(tzinfo=None)
    chats = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "agent.chat", AuditLog.created_at >= since)) or 0
    comps.append(Component("agent", "Agent 대화 (LangGraph)", "ok", f"최근 24시간 대화 {chats}건 · 규칙 Supervisor → 업무 Agent 4개", "Agent"))
    return Group("agent", "A2X Agent", "컨설팅 · 자동 채움 · 개발 지원 · 오류 조치", comps)


def _gateways(runtime, recent: list[CallLog]) -> list[Group]:
    reached, ms, code, body, err = runtime
    url = settings.CONVERTER_PUBLIC_URL.rstrip("/") + "/health"
    body = body if isinstance(body, dict) else {}
    mcp_recent = [r for r in recent if r.kind.value == "MCP"]
    t_all, t_mcp = _traffic(recent), _traffic(mcp_recent)

    # MCP 권한 Gateway: 지금은 A2X 런타임 안의 권한 판정(is_tool_permitted). 정책(구독 · Tool 권한)은 포탈 DB에서 읽는다
    perm = []
    if not reached:
        perm.append(Component("policy", "권한 판정 (구독 · Tool 권한)", "down", f"런타임에 닿지 않아 판정 불가 — {err}", "Gateway", endpoint=url))
    elif body.get("policy_db") != "ok":
        perm.append(Component("policy", "권한 판정 (구독 · Tool 권한)", "down", f"정책 DB 조회 실패: {body.get('policy_db', '알 수 없음')}", "Gateway", ms, url))
    else:
        enforce = body.get("enforce_permissions", True)
        perm.append(Component("policy", "권한 판정 (구독 · Tool 권한)", "ok" if enforce else "warn",
                              f"정책 DB {body.get('policy_db_ms', '-')}ms · " + ("호출마다 집행" if enforce else "집행 꺼짐(CONVERTER_ENFORCE_PERMISSIONS=false)"),
                              "Gateway", ms, url))
    denied = t_mcp["denied"]
    ratio = denied / t_mcp["calls"] * 100 if t_mcp["calls"] else 0
    perm.append(Component("denied", "권한 거부 (최근 1시간)", "warn" if ratio >= 30 and denied >= 5 else "ok",
                          f"MCP 호출 {t_mcp['calls']}건 중 거부 {denied}건" + (" — 거부가 많습니다(권한 신청 누락 · 오남용 확인)" if ratio >= 30 and denied >= 5 else ""),
                          "Policy", metrics={"denied": denied}))

    gw = []
    if reached:
        st = "warn" if (ms or 0) > SLOW_WARN_MS else "ok"
        gw.append(Component("runtime", "A2X MCP 런타임 (중계)", st, f"가동 {_fmt_uptime(body.get('uptime_s', 0))} · 변환 MCP → 원본 API, 직접 개발 MCP → 원본 MCP", "Runtime", ms, url))
    else:
        gw.append(Component("runtime", "A2X MCP 런타임 (중계)", "down", f"{err} — 변환 · 중계 호출이 모두 실패합니다", "Runtime", None, url))
    gw.append(Component("traffic", "트래픽 (최근 1시간)", _traffic_status(t_all),
                        f"호출 {t_all['calls']}건 · 오류율 {t_all['error_rate']}% · p95 {t_all['p95_ms']}ms · 5xx {t_all['server_errors']}건", "Traffic", metrics=t_all))
    gw.append(Component("wso2", "API Gateway (WSO2)", "off", "미도입 — 3차(Gateway 계층)에서 이 런타임을 옮길 예정", "Gateway"))
    return [
        Group("perm-gw", "MCP 권한 Gateway", "호출마다 시스템 구독 + 사용자 Tool 권한을 집행", perm),
        Group("data-gw", "MCP · API Gateway (Data plane)", "MCP 호출을 원본 API · MCP로 중계하고 호출 로그를 남김", gw),
    ]


def _mcp_servers(assets: list[Asset], probes: dict[int, Any], runtime_ok: bool, per_asset: dict[int, list[CallLog]]) -> Group:
    comps = []
    for a in assets:
        t = _traffic(per_asset.get(a.id, []))
        host = a.host_server.hostname if a.host_server else ("A2X 런타임" if a.source == AssetSource.MCP_CONVERTED else "-")
        stage = "운영" if a.status == AssetStatus.LIVE else "스테이지"
        base = f"{a.system.code} · {stage} · {host} · 24시간 호출 {t['calls']}건 · 오류율 {t['error_rate']}%"
        metrics = {**t, "system": a.system.code, "host": host, "source": a.source.value}
        if a.source == AssetSource.MCP_CONVERTED:
            status = "down" if not runtime_ok else _traffic_status(t)
            detail = ("A2X 런타임 중단 — " if not runtime_ok else "변환 MCP(런타임에서 실행) · ") + base
            comps.append(Component(f"mcp-{a.id}", a.name, status, detail, "변환 MCP", None, f"{settings.CONVERTER_PUBLIC_URL.rstrip('/')}/mcp/{a.id}", metrics))
            continue
        url = a.endpoint or ""
        if not url:
            comps.append(Component(f"mcp-{a.id}", a.name, "warn", "엔드포인트 미등록 · " + base, "컨테이너", None, "", metrics))
        elif _is_sample(url):
            comps.append(Component(f"mcp-{a.id}", a.name, "off", "샘플 주소 — 실제 연결 점검 제외 · " + base, "컨테이너", None, url, metrics))
        else:
            reached, ms, code, _b, err = probes[a.id]
            if not reached:
                comps.append(Component(f"mcp-{a.id}", a.name, "down", f"{err} · " + base, "컨테이너", None, url, metrics))
            else:
                st = worst([_traffic_status(t), "warn" if (ms or 0) > SLOW_WARN_MS else "ok"])
                comps.append(Component(f"mcp-{a.id}", a.name, st, f"응답함 HTTP {code} · " + base, "컨테이너", ms, url, metrics))
    comps.sort(key=lambda c: -RANK[c.status])
    return Group("mcp-servers", "MCP 서버 (서버 · 컨테이너별)", "운영 · 스테이지 상태의 MCP 서버. 직접 개발 MCP는 엔드포인트 연결, 변환 MCP는 런타임 상태로 판정", comps)


def _ops(db: Session, now: datetime) -> Group:
    comps = []
    last = db.scalar(select(func.max(CallLog.started_at)))
    hour = db.scalar(select(func.count()).select_from(CallLog).where(CallLog.started_at >= (now - timedelta(hours=1)).replace(tzinfo=None))) or 0
    stale = last is None or (now - _utc(last)) > timedelta(hours=LOG_STALE_HOURS)
    comps.append(Component("call-log", "호출 로그 수집", "warn" if stale else "ok",
                           f"마지막 호출 {_ago(last, now)} · 최근 1시간 {hour}건" + (" — 로그가 쌓이지 않습니다(런타임 · 로그 기록 확인)" if stale else ""), "Log"))
    try:
        du = shutil.disk_usage(ROOT_DIR)
        free = du.free / du.total * 100
        status = "down" if free < DISK_DOWN else "warn" if free < DISK_WARN else "ok"
        comps.append(Component("disk", "디스크", status, f"남은 공간 {du.free / 1024**3:.1f}GB ({free:.0f}%)", "Disk", metrics={"free_pct": round(free, 1)}))
    except OSError as e:
        comps.append(Component("disk", "디스크", "warn", f"확인 실패: {e}", "Disk"))
    sizes = {
        "벡터 DB": _dir_size(ROOT_DIR / settings.CHROMA_PERSIST_DIR.lstrip("./")),
        "업로드 문서": _dir_size(ROOT_DIR / settings.UPLOAD_DIR.lstrip("./")),
    }
    comps.append(Component("storage", "저장소 크기", "ok", " · ".join(f"{k} {_mb(v)}" for k, v in sizes.items()), "Storage"))
    return Group("ops", "운영 데이터", "호출 로그 · 디스크 · 저장소", comps)


# ---------------- 전체 점검 ----------------

_cache: dict[str, Any] = {}


async def check_all(db: Session, now: datetime | None = None, use_cache: bool = True) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if use_cache and _cache.get("at") and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]

    assets = [*db.scalars(select(Asset).where(Asset.type == AssetType.MCP, Asset.status.in_([AssetStatus.LIVE, AssetStatus.STAGE])).order_by(Asset.id))]
    direct = [a for a in assets if a.source == AssetSource.MCP_DIRECT and a.endpoint and not _is_sample(a.endpoint)]
    externals = [("master", "마스터 MCP (API · MCP 서버 마스터)", settings.MASTER_MCP_URL), ("irp", "IRP MCP (시스템 마스터)", settings.IRP_MCP_URL),
                 ("dcm", "DCM MCP (서버 자산)", settings.DCM_MCP_URL)]

    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=False) as client:
        results = await asyncio.gather(
            probe(client, settings.FRONTEND_URL),
            probe(client, settings.CONVERTER_PUBLIC_URL.rstrip("/") + "/health", want_json=True),
            *(probe(client, a.endpoint, mcp=True) for a in direct),
            *(probe(client, u, mcp=True) for _, _, u in externals),
        )
    frontend, runtime = results[0], results[1]
    direct_res = dict(zip((a.id for a in direct), results[2 : 2 + len(direct)]))
    ext_res = results[2 + len(direct) :]

    recent = [*db.scalars(select(CallLog).where(CallLog.started_at >= (now - timedelta(hours=1)).replace(tzinfo=None)))]
    day = [*db.scalars(select(CallLog).where(CallLog.started_at >= (now - timedelta(hours=24)).replace(tzinfo=None), CallLog.asset_id.in_([a.id for a in assets])))]
    per_asset: dict[int, list[CallLog]] = {}
    for r in day:
        per_asset.setdefault(r.asset_id, []).append(r)

    runtime_ok = bool(runtime[0]) and isinstance(runtime[3], dict) and runtime[3].get("policy_db") == "ok"
    groups = [
        _portal(db, now, frontend),
        *_gateways(runtime, recent),
        _mcp_servers(assets, direct_res, runtime_ok, per_asset),
        Group("external", "외부 연계 MCP", "자동 채움 · 오류 조치가 읽는 외부 시스템 MCP(1차는 모의 서버 8200)",
              [_reach(k, n, u, res, "외부 MCP", "MCP 서버 응답") for (k, n, u), res in zip(externals, ext_res)]),
        _agent(db, now),
        _ops(db, now),
    ]
    all_comps = [c for g in groups for c in g.components]
    data = {
        "checked_at": now.isoformat(),
        "status": worst(c.status for c in all_comps),  # off는 정상으로 친다
        "counts": {s: sum(c.status == s for c in all_comps) for s in ("ok", "warn", "down", "off")},
        "host": {"name": platform.node(), "os": f"{platform.system()} {platform.release()}", "python": sys.version.split()[0]},
        "groups": [{"key": g.key, "label": g.label, "desc": g.desc, "status": g.status, "components": [asdict(c) for c in g.components]} for g in groups],
    }
    _cache.update(at=time.time(), data=data)
    return data
