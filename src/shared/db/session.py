"""DB 연결과 세션.

DB 방언에 따른 처리는 이 파일에만 둔다(SQLite 외래 키 활성화, 상대 경로 처리).
PostgreSQL로 바꿀 때는 DATABASE_URL만 바꾸면 된다.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.shared.config import ROOT_DIR, settings


def normalize_url(url: str) -> str:
    """SQLite 상대 경로를 저장소 루트 기준 절대 경로로 바꾼다."""
    u = make_url(url)
    if u.get_backend_name() == "sqlite" and u.database and u.database != ":memory:":
        p = Path(u.database)
        if not p.is_absolute():
            u = u.set(database=str((ROOT_DIR / p).resolve()))
    return u.render_as_string(hide_password=False)


def make_engine(url: str, echo: bool = False) -> Engine:
    url = normalize_url(url)
    is_sqlite = url.startswith("sqlite")
    kwargs: dict = {"echo": echo, "future": True}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url.endswith("sqlite://"):
            kwargs["poolclass"] = StaticPool  # 테스트용 메모리 DB를 연결 사이에 공유
    engine = create_engine(url, **kwargs)

    if is_sqlite:
        # SQLite는 외래 키 검사가 기본으로 꺼져 있다
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - 연결 시점 훅
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = make_engine(settings.DATABASE_URL, echo=settings.DATABASE_ECHO)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 의존성: 요청마다 세션 하나. 커밋은 서비스 계층이 한다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope(factory: sessionmaker = SessionLocal) -> Iterator[Session]:
    """스크립트용: 블록이 끝나면 커밋, 예외면 롤백."""
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
