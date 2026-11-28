from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# 저장소 루트 (src/shared/config.py 기준 두 단계 위).
# .env와 SQLite 상대 경로는 실행 위치와 상관없이 이 루트를 기준으로 한다.
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "A2X"
    APP_ENV: str = "development"
    PORT: int = 8000
    DEBUG: bool = True

    # 프런트엔드 출처. 쿠키 인증을 쓰므로 "*" 대신 명시한다 (.env에서는 JSON 배열로 지정)
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    SECRET_KEY: str = "temporary-dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Google 로그인(OAuth 2.0 + PKCE). 값은 .env에서 읽는다. 비우면 Google 로그인 버튼을 숨긴다
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    GOOGLE_ALLOWED_DOMAINS: list[str] = []  # 예: ["example.com"]. 비우면 모든 도메인(.env에서는 JSON 배열)
    FRONTEND_URL: str = "http://localhost:5173/"  # 로그인 후 돌아갈 포탈 주소
    # 개발용 권한 스위치(오른쪽 위에서 내 역할 바꾸기). 비우면 APP_ENV=development일 때만 켜진다. 운영에서는 반드시 꺼야 한다
    DEV_ROLE_SWITCH: Optional[bool] = None

    DATABASE_URL: str = "sqlite:///./a2x.db"
    DATABASE_ECHO: bool = False

    # Anthropic LLM
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-5-5"
    ANTHROPIC_FALLBACK_MODEL: str = "claude-haiku-5-5"
    LLM_SERVER_FALLBACK: bool = True  # Sonnet 5.5 등: 안전 거절 시 API가 다른 모델로 다시 돌림(fallbacks: "default")
    LLM_TIMEOUT_SECONDS: float = 60.0

    # API → MCP 컨버터 런타임 (Data plane, 별도 프로세스)
    PORTAL_PUBLIC_URL: str = "http://localhost:8000"  # 개발 지원 Agent의 포탈 API 예시 주소
    CONVERTER_PUBLIC_URL: str = "http://localhost:8100"  # 변환 MCP 서버 엔드포인트 = 이 주소 + /mcp/{자산ID}
    CONVERTER_ENFORCE_PERMISSIONS: bool = True  # 사용자 · 시스템 구독 · Tool 권한 확인
    CONVERTER_ALLOWED_HOSTS: list[str] = []  # 비우면 DNS rebinding 보호를 끈다(개발용)
    # 원본 API 인증 토큰: A2X_UPSTREAM_TOKEN_<시스템코드> 환경변수(.env)에서 읽는다

    # A2X Agent
    MASTER_MCP_URL: str = "http://localhost:8200/mcp"  # 외부 마스터 MCP 서버(API · MCP 서버 마스터 · 연락처, 1차는 모의 서버)
    IRP_MCP_URL: str = "http://localhost:8200/irp/mcp"  # IRP(전사 IT 자원 · 시스템 마스터) MCP — 시스템 등록 자동 채움
    DCM_MCP_URL: str = "http://localhost:8200/dcm/mcp"  # DCM(데이터센터 서버 자산) MCP — 서버 등록 자동 채움
    # A2X Agent 자신도 시스템이다: 다른 시스템의 MCP는 이 시스템의 구독으로 A2X 중계(CONVERTER_PUBLIC_URL/mcp/{자산ID})를 거쳐 부른다
    A2X_AGENT_SYSTEM_CODE: str = "A2X"
    AGENT_VIA_A2X: bool = True  # False면 원본 MCP에 바로 접속(개발 · 테스트용)
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    RAG_WARMUP: bool = True  # 서버 시작 시 임베딩 모델을 백그라운드로 미리 불러온다(첫 검색 20초대 지연 방지, 테스트는 끔)
    # 근거 판정(src/knowledge/evidence.py): (유사도 >= MIN 그리고 핵심어 포함률 >= COVERAGE) 또는 유사도 >= STRONG
    RAG_MIN_SCORE: float = 0.2
    RAG_MIN_COVERAGE: float = 0.6
    RAG_STRONG_SCORE: float = 0.6

    # Vector DB
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # 업로드 파일 저장 위치(컨설팅 문서). 상대 경로는 저장소 루트 기준
    UPLOAD_DIR: str = "./uploads"
    CONSULT_DOC_MAX_BYTES: int = 5 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def dev_role_switch_enabled() -> bool:
    return settings.DEV_ROLE_SWITCH if settings.DEV_ROLE_SWITCH is not None else settings.APP_ENV == "development"
