"""마이그레이션이 모델과 같은 스키마를 만드는지 확인한다."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

import src.models  # noqa: F401
from src.shared.db.base import Base
from src.shared.db.session import make_engine

ROOT = Path(__file__).resolve().parents[1]  # 저장소 루트(alembic.ini · alembic/)


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.attributes["url"] = url
    return cfg


def test_upgrade_matches_models(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(_config(url), "head")

    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"모델과 마이그레이션이 다릅니다: {diff}"
    engine.dispose()


def test_downgrade_to_base(tmp_path):
    url = f"sqlite:///{(tmp_path / 'd.db').as_posix()}"
    cfg = _config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = make_engine(url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
