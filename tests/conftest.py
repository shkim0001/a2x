import pytest
from sqlalchemy.orm import Session, sessionmaker

import src.models  # noqa: F401  모든 모델 등록
from src.shared.config import settings

settings.RAG_WARMUP = False  # 테스트에서는 실제 임베딩 모델을 미리 불러오지 않는다
from src.shared.db.base import Base
from src.shared.db.session import make_engine


@pytest.fixture()
def engine():
    eng = make_engine("sqlite://")  # 메모리 DB
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(session_factory) -> Session:
    s = session_factory()
    yield s
    s.close()


@pytest.fixture()
def seeded(db):
    from src.seed import seed

    seed(db)
    db.commit()
    return db


@pytest.fixture()
def client(session_factory, seeded):
    """시드된 메모리 DB를 쓰는 API 클라이언트."""
    from fastapi.testclient import TestClient

    from src.shared.db.session import get_db
    from src.main import app

    def _db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


DEV_PASSWORD = "a2x-demo-1234"


def login(client, email: str) -> dict:
    """로그인하고 Bearer 헤더를 돌려준다(쿠키 대신 헤더로 사용자를 바꿔 가며 호출하기 위함)."""
    r = client.post("/api/v1/auth/login", json={"email": email, "password": DEV_PASSWORD})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def as_user(client):
    return lambda email: login(client, email)
