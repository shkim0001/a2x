"""지식(컨설팅 문서) 도메인 모델."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base, TimestampMixin, enum_type

from enum import StrEnum


class DocStatus(StrEnum):
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class ConsultDoc(TimestampMixin, Base):
    __tablename__ = "consult_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500), default="")
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[DocStatus] = mapped_column(enum_type(DocStatus, "doc_status"), default=DocStatus.INDEXING)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(500), default="")  # 색인 실패 사유


