"""기준정보 도메인 모델: 시스템 · 담당자 · 서버와 코드값."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.auth.models import User
from src.shared.db.base import Base, enum_type, TimestampMixin

from enum import StrEnum


class SystemKind(StrEnum):
    BUSINESS = "BUSINESS"  # 업무 시스템
    AGENT = "AGENT"  # AI Agent


class DataLevel(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"


class ServerEnv(StrEnum):
    PROD = "PROD"
    STAGE = "STAGE"
    DEV = "DEV"


class System(TimestampMixin, Base):
    """관리 단위. 업무 시스템과 AI Agent 모두 시스템이다."""

    __tablename__ = "systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[SystemKind] = mapped_column(enum_type(SystemKind, "system_kind"))
    process: Mapped[str] = mapped_column(String(30))  # 업무 프로세스(분류 체계는 바뀔 수 있어 문자열)
    dept: Mapped[str] = mapped_column(String(100), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    data_level: Mapped[DataLevel] = mapped_column(enum_type(DataLevel, "data_level"), default=DataLevel.INTERNAL)
    description: Mapped[str] = mapped_column(Text, default="")

    managers: Mapped[list["SystemManager"]] = relationship(back_populates="system", cascade="all, delete-orphan", lazy="selectin")
    servers: Mapped[list["Server"]] = relationship(back_populates="system", cascade="all, delete-orphan", lazy="selectin", order_by="Server.id")

    @property
    def manager_users(self) -> list[User]:
        return [m.user for m in self.managers]

    def is_manager(self, user_id: int) -> bool:
        return any(m.user_id == user_id for m in self.managers)


class SystemManager(Base):
    """시스템 담당자(N명). 추가는 승인 없이 바로 반영한다."""

    __tablename__ = "system_managers"

    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    system: Mapped[System] = relationship(back_populates="managers")
    user: Mapped[User] = relationship(lazy="joined")


class Server(TimestampMixin, Base):
    __tablename__ = "servers"
    __table_args__ = (UniqueConstraint("system_id", "hostname"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), index=True)
    hostname: Mapped[str] = mapped_column(String(100))
    ip: Mapped[str] = mapped_column(String(45))  # IPv6까지
    port: Mapped[int] = mapped_column(Integer)
    env: Mapped[ServerEnv] = mapped_column(enum_type(ServerEnv, "server_env"), default=ServerEnv.PROD)
    role: Mapped[str] = mapped_column(String(50), default="")  # 용도: WAS, API, MCP, Agent …

    system: Mapped[System] = relationship(back_populates="servers")


