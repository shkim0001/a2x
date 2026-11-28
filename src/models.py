"""모든 도메인 모델을 등록한다(SQLAlchemy 메타데이터 · 관계 구성). Alembic env · 테스트 · 앱 시작에서 import한다.

모델 자체는 각 도메인의 models.py에 있다. 새 도메인 모델을 만들면 여기에 한 줄 추가한다.
"""

from src.audit.models import AuditLog
from src.auth.models import AuthSession, User
from src.catalog.models import ApiLayoutField, ApiOperation, Asset, McpTool
from src.knowledge.models import ConsultDoc
from src.monitoring.models import CallLog
from src.subscriptions.models import SystemSubscription, ToolRequest
from src.systems.models import Server, System, SystemManager

__all__ = [
    "ApiLayoutField", "ApiOperation", "Asset", "AuditLog", "AuthSession", "CallLog", "ConsultDoc", "McpTool",
    "Server", "System", "SystemManager", "SystemSubscription", "ToolRequest", "User",
]
