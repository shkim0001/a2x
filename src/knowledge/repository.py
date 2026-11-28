"""지식(컨설팅 문서) 도메인 저장소."""

from __future__ import annotations

from src.knowledge.models import ConsultDoc
from src.shared.db.repository import Repository


class ConsultDocRepository(Repository[ConsultDoc]):
    model = ConsultDoc
