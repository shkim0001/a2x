"""Alembic 환경: DB 주소와 메타데이터를 앱 설정 · 모델에서 가져온다."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# 저장소 루트를 import 경로에 넣는다 (src... 절대 import)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shared.config import settings  # noqa: E402
from src.shared.db.base import Base  # noqa: E402
from src.shared.db.session import make_engine, normalize_url  # noqa: E402
import src.models  # noqa: E402,F401  모든 모델 등록

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # 테스트 등에서 -x url=... 또는 config 속성으로 덮어쓸 수 있다
    return config.attributes.get("url") or context.get_x_argument(as_dictionary=True).get("url") or settings.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=normalize_url(_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        engine = make_engine(_url())
        with engine.connect() as connection:
            _run(connection)
        engine.dispose()
    else:
        _run(connectable)


def _run(connection) -> None:
    # SQLite는 ALTER TABLE 제약이 많아 batch 모드로 마이그레이션한다(PostgreSQL에서도 문제없음)
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
