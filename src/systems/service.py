"""기준정보 규칙: 시스템 · 담당자 · 서버 관리(해당 시스템 담당자 또는 admin)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.audit.repository import AuditRepository
from src.auth.models import User
from src.auth.repository import UserRepository
from src.catalog.models import Asset
from src.shared.config import settings
from src.shared.errors import Conflict, Invalid, NotFound
from src.subscriptions.repository import SubscriptionRepository
from src.systems.access import ensure_can_manage
from src.systems.models import Server, System, SystemManager
from src.systems.repository import ServerRepository, SystemRepository
from src.systems.schemas import ServerIn, SystemIn, SystemUpdate


def _audit(db: Session, user: User, action: str, target_type: str, target_id, detail: dict | None = None) -> None:
    AuditRepository(db).record(user.id, action, target_type, target_id, detail)


def get_system(db: Session, system_id: int) -> System:
    s = SystemRepository(db).get(system_id)
    if s is None:
        raise NotFound("시스템을 찾을 수 없습니다.")
    return s


def create_system(db: Session, user: User, data: SystemIn) -> System:
    repo = SystemRepository(db)
    code = data.code.upper()
    if repo.get_by_code(code):
        raise Conflict(f"시스템 코드 '{code}'가 이미 있습니다.", "code_taken")
    users = UserRepository(db)
    extra = []
    for email in data.manager_emails:
        u = users.get_by_email(email)
        if u is None:
            raise NotFound(f"사용자 {email}을(를) 찾을 수 없습니다.", "user_not_found")
        extra.append(u)
    s = System(code=code, name=data.name, kind=data.kind, process=data.process, dept=data.dept, url=data.url, data_level=data.data_level, description=data.description)
    # 등록자가 첫 담당자. 담당자 추가는 승인 없이 바로 반영
    for u in [user, *[e for e in extra if e.id != user.id]]:
        s.managers.append(SystemManager(user=u))
    _check_servers_unique(data.servers)
    s.servers = [Server(**sv.model_dump()) for sv in data.servers]
    repo.add(s)
    _audit(db, user, "system.create", "system", s.id, {"code": code})
    return s


def update_system(db: Session, user: User, system_id: int, data: SystemUpdate) -> System:
    s = get_system(db, system_id)
    ensure_can_manage(user, s)
    changes = data.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(s, k, v)
    db.flush()
    _audit(db, user, "system.update", "system", s.id, {"fields": sorted(changes)})
    return s


def delete_system(db: Session, user: User, system_id: int) -> None:
    """시스템 삭제: 등록한 API · MCP가 있거나 이 시스템이 클라이언트인 승인 대기 · 승인 구독이 있으면 막는다.
    서버 · 담당자 연결은 함께 지우고, 끝난 구독 이력도 정리한다(호출 로그 · 감사 로그는 남음)."""
    s = get_system(db, system_id)
    ensure_can_manage(user, s)
    if s.code == settings.A2X_AGENT_SYSTEM_CODE:
        raise Invalid("A2X 내장 Agent 시스템은 삭제할 수 없습니다.", "builtin_system")
    assets = [*db.scalars(select(Asset).where(Asset.system_id == s.id))]
    if assets:
        raise Conflict(f"이 시스템의 API · MCP {len(assets)}개({', '.join(a.name for a in assets[:3])}{' 등' if len(assets) > 3 else ''})를 먼저 삭제하세요.", "system_has_assets")
    subs = SubscriptionRepository(db)
    active = subs.active_of(client_system_id=s.id)
    if active:
        raise Conflict(f"이 시스템의 구독 {len(active)}건(승인 · 대기)을 먼저 해지하세요.", "system_in_use")
    purged = subs.purge_ended(client_system_id=s.id)
    _audit(db, user, "system.delete", "system", s.id, {"code": s.code, "servers": len(s.servers), "managers": len(s.managers), "ended_subscriptions": purged})
    db.delete(s)
    db.flush()


def add_manager(db: Session, user: User, system_id: int, email: str) -> System:
    s = get_system(db, system_id)
    ensure_can_manage(user, s)
    target = UserRepository(db).get_by_email(email)
    if target is None:
        raise NotFound(f"사용자 {email}을(를) 찾을 수 없습니다.", "user_not_found")
    if not SystemRepository(db).add_manager(s, target):
        raise Conflict("이미 담당자입니다.", "already_manager")
    _audit(db, user, "system.manager.add", "system", s.id, {"user_id": target.id})
    return s


def remove_manager(db: Session, user: User, system_id: int, target_user_id: int) -> System:
    s = get_system(db, system_id)
    ensure_can_manage(user, s)
    link = next((m for m in s.managers if m.user_id == target_user_id), None)
    if link is None:
        raise NotFound("담당자가 아닙니다.")
    if len(s.managers) == 1:
        raise Invalid("담당자는 최소 한 명이어야 합니다.", "last_manager")
    s.managers.remove(link)
    db.flush()
    _audit(db, user, "system.manager.remove", "system", s.id, {"user_id": target_user_id})
    return s


def _check_servers_unique(servers: list[ServerIn]) -> None:
    names = [s.hostname for s in servers]
    if len(names) != len(set(names)):
        raise Invalid("같은 호스트명이 두 번 들어 있습니다.", "duplicate_hostname")


def add_server(db: Session, user: User, system_id: int, data: ServerIn) -> Server:
    s = get_system(db, system_id)
    ensure_can_manage(user, s)
    if any(sv.hostname == data.hostname for sv in s.servers):
        raise Conflict(f"호스트명 '{data.hostname}'이(가) 이미 있습니다.", "duplicate_hostname")
    server = Server(system_id=s.id, **data.model_dump())
    s.servers.append(server)
    db.flush()
    _audit(db, user, "server.add", "system", s.id, {"hostname": data.hostname})
    return server


def update_server(db: Session, user: User, server_id: int, data: ServerIn) -> Server:
    server = ServerRepository(db).get(server_id)
    if server is None:
        raise NotFound("서버를 찾을 수 없습니다.")
    ensure_can_manage(user, server.system)
    if any(sv.id != server.id and sv.hostname == data.hostname for sv in server.system.servers):
        raise Conflict(f"호스트명 '{data.hostname}'이(가) 이미 있습니다.", "duplicate_hostname")
    before = server.hostname
    for k, v in data.model_dump().items():
        setattr(server, k, v)
    db.flush()
    _audit(db, user, "server.update", "system", server.system_id, {"hostname": data.hostname, "before": before})
    return server


def delete_server(db: Session, user: User, server_id: int) -> None:
    server = ServerRepository(db).get(server_id)
    if server is None:
        raise NotFound("서버를 찾을 수 없습니다.")
    ensure_can_manage(user, server.system)
    in_use = db.scalar(select(func.count()).select_from(Asset).where(Asset.host_server_id == server.id))
    if in_use:
        raise Conflict("이 서버를 쓰는 MCP 서버가 있어 삭제할 수 없습니다.", "server_in_use")
    _audit(db, user, "server.delete", "system", server.system_id, {"hostname": server.hostname})
    server.system.servers.remove(server)
    db.flush()


def list_servers(db: Session, user: User, q: str | None, env, process: str | None, mine: bool) -> list[tuple[Server, System]]:
    stmt = select(Server, System).join(System, Server.system_id == System.id)
    if env:
        stmt = stmt.where(Server.env == env)
    if process:
        stmt = stmt.where(System.process == process)
    if mine:
        stmt = stmt.where(System.id.in_(SystemRepository(db).managed_ids(user.id)))
    rows = [(sv, sy) for sv, sy in db.execute(stmt.order_by(System.id, Server.id)).unique()]
    if q:
        ql = q.lower()
        rows = [(sv, sy) for sv, sy in rows if any(ql in v.lower() for v in (sv.hostname, sv.ip, sv.role, sy.name, sy.code))]
    return rows


def system_label(code: str, name: str) -> str:
    """화면 · Agent 답변용 시스템 표시. 이름이 코드와 같으면(영문 약어) 코드만, 다르면 '코드 이름'."""
    return code if (name or "").strip().upper() == code.upper() else f"{code} {name}"
