"""권한 판정 규칙 (Python 코드로 판정, LLM 사용 안 함).

- admin(저장된 역할): 모든 관리 작업, 등록 승인
- 시스템 담당자(계산): 담당 시스템이 하나라도 있는 사용자. 담당 시스템의 정보 · 서버 · 자산 관리,
  담당 시스템을 대상으로 한 구독 · Tool 신청 승인, 담당 시스템(클라이언트)으로 시스템 구독 신청
- 모든 사용자: 카탈로그 조회, 승인된 MCP 연계 안에서 Tool 사용 신청, 새 시스템 등록(등록하면 담당자가 됨)
"""

from sqlalchemy.orm import Session

from src.auth.models import Role, User
from src.shared.errors import Forbidden
from src.systems.models import System
from src.systems.repository import SystemRepository


def is_admin(user: User) -> bool:
    return user.role == Role.ADMIN


def effective_role(db: Session, user: User) -> str:
    """화면에 쓰는 역할(ADMIN · MANAGER · USER). admin만 저장하고, 나머지는 담당 시스템이 있으면 MANAGER로 계산한다.

    화면 메뉴 · 버튼을 고르는 데만 쓴다. 승인 · 관리 같은 실제 권한은 '그 시스템의 담당자인가'(can_manage_system 등)로 판정한다.
    """
    if is_admin(user):
        return Role.ADMIN.value
    return "MANAGER" if SystemRepository(db).managed_ids(user.id) else Role.USER.value


def can_manage_system(user: User, system: System) -> bool:
    return is_admin(user) or system.is_manager(user.id)


def ensure_can_manage(user: User, system: System) -> None:
    if not can_manage_system(user, system):
        raise Forbidden(f"'{system.name}' 시스템의 담당자만 할 수 있습니다.", "not_system_manager")


def ensure_admin(user: User) -> None:
    if not is_admin(user):
        raise Forbidden("admin만 할 수 있습니다.", "admin_only")
