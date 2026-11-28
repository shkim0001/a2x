"""감사 도메인 저장소."""

from __future__ import annotations

from typing import Any

from src.audit.models import AuditLog
from src.shared.db.repository import Repository


class AuditRepository(Repository[AuditLog]):
    model = AuditLog

    def record(self, actor_id: int | None, action: str, target_type: str, target_id: Any, detail: dict | None = None) -> AuditLog:
        return self.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=str(target_id), detail=detail))
