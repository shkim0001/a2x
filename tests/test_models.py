import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError

from src.audit.repository import AuditRepository
from src.auth.models import Role, User
from src.auth.repository import UserRepository
from src.catalog.models import Asset, AssetSource, AssetStatus, AssetType, McpTool
from src.catalog.repository import AssetRepository
from src.subscriptions.models import RequestStatus, SystemSubscription, ToolRequest
from src.subscriptions.repository import SubscriptionRepository, ToolRequestRepository
from src.systems.models import Server, System, SystemKind, SystemManager
from src.systems.repository import SystemRepository


def _system(db, code="SYS1", kind=SystemKind.BUSINESS):
    s = System(code=code, name=f"{code} 시스템", kind=kind, process="물류")
    db.add(s)
    db.flush()
    return s


def test_seed_counts(seeded):
    assert SystemRepository(seeded).count() == 13  # IRP · DCM · A2X Agent 포함
    assert AssetRepository(seeded).count() == 17
    assert SubscriptionRepository(seeded).count() == 17  # A2X Agent → IRP · DCM MCP 포함
    assert ToolRequestRepository(seeded).count() == 13 + 21 * 3  # 담당자 · admin 21명에게 A2X Agent 조회 Tool 3개 일괄 승인


def test_system_managers_and_servers(seeded):
    repo = SystemRepository(seeded)
    wms = repo.get_by_code("wms")
    assert {u.name for u in wms.manager_users} == {"홍길동", "최물류", "설두환"}
    assert [s.hostname for s in wms.servers] == ["wms-api01", "wms-mcp01"]
    hong = UserRepository(seeded).get_by_email("HONG@example.com ")
    assert repo.managed_ids(hong.id) == {wms.id, repo.get_by_code("CSBOT").id}


def test_add_manager_is_idempotent(seeded):
    repo = SystemRepository(seeded)
    erp = repo.get_by_code("ERP")
    kim = UserRepository(seeded).get_by_email("kim@example.com")
    assert repo.add_manager(erp, kim) is True
    assert repo.add_manager(erp, kim) is False
    assert erp.is_manager(kim.id)


def test_duplicate_manager_row_rejected(db):
    s = _system(db)
    u = User(email="a@example.com", name="a")
    db.add(u)
    db.flush()
    db.add(SystemManager(system_id=s.id, user_id=u.id))
    db.flush()
    db.add(SystemManager(system_id=s.id, user_id=u.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_system_code_unique(db):
    _system(db, "DUP")
    db.add(System(code="DUP", name="x", kind=SystemKind.BUSINESS, process="물류"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_system_cascades_servers(db):
    s = _system(db)
    s.servers.append(Server(hostname="h1", ip="10.0.0.1", port=80))
    db.flush()
    db.delete(s)
    db.flush()
    assert db.scalars(select(Server)).all() == []


def test_asset_type_source_check(db):
    s = _system(db)
    db.add(Asset(system_id=s.id, type=AssetType.API, source=AssetSource.MCP_DIRECT, name="잘못된 자산"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_enum_rejects_unknown_value(db):
    db.add(User(email="b@example.com", name="b", role="SUPERUSER"))
    with pytest.raises((StatementError, LookupError)):
        db.flush()


def test_asset_with_subscription_cannot_be_deleted(seeded):
    order = AssetRepository(seeded).catalog(q="주문 조회")[0]
    seeded.delete(order)
    with pytest.raises(IntegrityError):
        seeded.flush()


def test_converted_mcp_links_to_source(seeded):
    mcp = AssetRepository(seeded).catalog(q="고객 정보 MCP")[0]
    assert mcp.source == AssetSource.MCP_CONVERTED
    assert mcp.converted_from.name == "고객 정보 API"
    get_customer = next(t for t in mcp.tools if t.name == "get_customer")
    assert get_customer.source_operation.path == "/customers/{customerId}"


def test_catalog_filters(seeded):
    repo = AssetRepository(seeded)
    assert len(repo.catalog(type_=AssetType.MCP)) == 8  # IRP · DCM MCP 포함
    assert {a.name for a in repo.catalog(status=AssetStatus.PENDING)} == {"생산 실적 API"}
    assert {a.name for a in repo.catalog(q="공급망")} == {"발주 관리 API", "공급사 정보 MCP", "수요 예측 API"}  # 부서명(공급망혁신팀) 검색


def test_active_subscription_lookup(seeded):
    sys_repo = SystemRepository(seeded)
    stock = AssetRepository(seeded).catalog(q="재고 MCP")[0]
    sub_repo = SubscriptionRepository(seeded)
    assert sub_repo.find_active(sys_repo.get_by_code("CSBOT").id, stock.id).status == RequestStatus.APPROVED
    assert sub_repo.find_active(sys_repo.get_by_code("MKT").id, stock.id) is None  # 반려 건은 활성이 아님


def test_provider_side_queues(seeded):
    sys_repo = SystemRepository(seeded)
    hong = UserRepository(seeded).get_by_email("hong@example.com")
    mine = sys_repo.managed_ids(hong.id)
    pending_subs = SubscriptionRepository(seeded).for_provider(mine, RequestStatus.PENDING)
    assert [s.client_system.code for s in pending_subs] == ["PURCH"]  # PURCH(구매 추천 Agent) → 재고 MCP
    pending_tools = ToolRequestRepository(seeded).for_provider(mine, RequestStatus.PENDING)
    assert [(t.user.name, t.tool.name) for t in pending_tools] == [("김민수", "reserve_stock")]


def test_tool_permission_check(seeded):
    users = UserRepository(seeded)
    hong, kim = users.get_by_email("hong@example.com"), users.get_by_email("kim@example.com")
    tr = ToolRequestRepository(seeded)
    req = next(r for r in tr.for_user(hong.id) if r.tool.name == "get_stock")
    assert tr.is_permitted(hong.id, req.subscription_id, req.tool_id)
    assert not tr.is_permitted(kim.id, req.subscription_id, req.tool_id)


def test_audit_record(seeded):
    admin = UserRepository(seeded).get_by_email("admin@example.com")
    log = AuditRepository(seeded).record(admin.id, "asset.approve", "asset", 3, {"to": "STAGE"})
    assert log.id and log.created_at and log.target_id == "3"


def test_roles_seeded(seeded):
    users = UserRepository(seeded).list()
    assert {u.role for u in users} == {Role.ADMIN, Role.USER}
    assert all(isinstance(t, McpTool) for t in seeded.scalars(select(McpTool)))
    assert seeded.scalars(select(ToolRequest)).first().subscription is not None
    assert isinstance(seeded.scalars(select(SystemSubscription)).first().asset, Asset)
