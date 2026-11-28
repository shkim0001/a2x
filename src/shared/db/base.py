"""SQLAlchemy 선언 기반.

DB 종류에 묶이지 않도록 공통 타입만 쓴다.
- 열거형은 문자열 + CHECK 제약(native_enum=False)으로 저장해 SQLite · PostgreSQL 모두 같은 스키마가 된다.
- 제약 이름 규칙을 고정해 Alembic 마이그레이션이 DB마다 달라지지 않게 한다.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def enum_type(enum_cls: type[enum.Enum], name: str) -> Enum:
    """문자열 + CHECK 제약으로 저장하는 열거형 컬럼 타입."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
