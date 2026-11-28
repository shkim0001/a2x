"""/api/v1 라우터 조립. 각 도메인의 router.py를 여기서 모은다(새 도메인 라우터는 여기에 한 줄 추가)."""

from fastapi import APIRouter

from src.agents import router as agents
from src.auth import router as auth, users_router
from src.catalog import layout_router, router as catalog
from src.converter import router as converter
from src.knowledge import router as knowledge
from src.monitoring import router as monitoring
from src.subscriptions import router as subscriptions
from src.systems import router as systems

api_router = APIRouter()
for module in (auth, users_router, systems, catalog, layout_router, subscriptions, converter, monitoring, knowledge, agents):
    api_router.include_router(module.router)


@api_router.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "service": "A2X API", "version": "0.1.0"}
