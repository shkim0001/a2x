import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api import api_router
from src.shared.config import settings
from src.shared.errors import ServiceError


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 컨설팅 RAG: 임베딩 모델을 백그라운드로 미리 불러온다(서버 시작은 기다리지 않음)
    if settings.RAG_WARMUP:
        from src.knowledge.store import warm_up

        threading.Thread(target=warm_up, name="rag-warmup", daemon=True).start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title=settings.APP_NAME,
        description="A2X (AI-to-X) 연계 거버넌스 플랫폼 API",
        version="0.1.0",
        debug=settings.DEBUG,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 서비스 계층 오류 → {"detail": 메시지, "code": 코드}
    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, "code": exc.code})

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/")
    def root():
        return {"message": "Welcome to A2X Platform API", "docs": "/docs"}

    return app


app = create_app()
