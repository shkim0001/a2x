# A2X Portal — AI 연계 거버넌스 플랫폼

사내 시스템을 API · MCP로 등록하고, AI Agent가 승인된 Tool만 호출하도록 관리하는 플랫폼입니다.
등록 → 승인 → 구독 · Tool 신청 → 호출(A2X 중계) → 모니터링까지 한 곳에서 다루고, 포탈 안의 A2X Agent가 상담 · 양식 채움 · 코드 예시 · 오류 조치를 돕습니다.

- 무엇을 만드는지: [SERVICE.md](SERVICE.md)
- 개발 규칙 · 명령어 · 폴더 구조: [CLAUDE.md](CLAUDE.md)
- A2X Agent 설계(라우팅 · 가드레일 · Tool): [AGENTS.md](AGENTS.md)
- 작업 이력과 남은 결정: [HISTORY.md](HISTORY.md)

## 구성

| 프로세스 | 포트 | 실행 모듈 | 역할 |
|---|---|---|---|
| 웹 포탈 | 5173 | `frontend/` (React · Vite) | 사용자 화면. `/api`는 8000으로 프록시 |
| 포탈 API | 8000 | `src.main:app` (FastAPI) | 기준정보 · 카탈로그 · 구독 · 모니터링 · A2X Agent |
| A2X MCP 런타임 | 8100 | `src.converter.server:app` | MCP 권한 Gateway + MCP/API 중계(변환 MCP → 원본 API, 직접 개발 MCP → 원본 MCP), 호출 로그 |
| 모의 외부 MCP | 8200 | `src.tools.mock_master.server:app` | 마스터 `/mcp` · IRP `/irp/mcp` · DCM `/dcm/mcp` (1차 개발용) |

Control plane(포탈 · Agent)과 Data plane(런타임)은 프로세스가 나뉘어 있고, 3차에 런타임을 Gateway(WSO2) 계층으로 옮길 예정입니다.
구성요소 상태는 포탈 '모니터링 › 인스턴스 모니터링'에서 봅니다.

## 처음 실행하기 (Windows)

준비: Python 3.13, Node 20.15 이상. 명령은 모두 저장소 루트에서 실행합니다.

```powershell
# 1) 백엔드 의존성
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) 설정: .env.example을 .env로 복사하고 필요한 값을 채운다(비밀 값은 커밋하지 않는다)
copy .env.example .env

# 3) DB 만들기 · 샘플 데이터(시스템 · 자산 · 구독 · 호출 로그 · 컨설팅 문서 색인)
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m src.seed

# 4) 프런트엔드 의존성
cd frontend; npm install; cd ..
```

시스템 PATH의 `python`은 Microsoft Store 바로가기라 동작하지 않을 수 있으니 `.venv\Scripts\python.exe`를 직접 씁니다.
임베딩 모델(sentence-transformers)은 처음 색인할 때 한 번 내려받습니다.

### 띄우기 (터미널 4개)

```powershell
.venv\Scripts\python.exe -m uvicorn src.main:app --reload --reload-dir src --port 8000
.venv\Scripts\python.exe -m uvicorn src.converter.server:app --port 8100
.venv\Scripts\python.exe -m uvicorn src.tools.mock_master.server:app --port 8200
cd frontend; npm run dev
```

브라우저에서 http://localhost:5173 을 엽니다. 포탈 API는 시작 후 약 20초 동안 임베딩 모델을 미리 불러오며, 그 사이의 첫 컨설팅 질문은 조금 기다립니다.

### 개발용 계정

비밀번호는 모두 `a2x-demo-1234`입니다.

| 계정 | 화면 |
|---|---|
| `admin@example.com` | admin(등록 승인 · 모든 구독 승인 · 컨설팅 문서) |
| `hong@example.com` | 시스템 담당자(WMS · CSBOT 등 담당) |
| `lee@example.com` | 담당 시스템 없는 사용자(카탈로그 · Tool 신청) |

역할은 admin만 저장하고, 시스템 담당자는 담당 시스템이 있으면 자동으로 됩니다.
개발 환경(`APP_ENV=development`)에서는 오른쪽 위 이름 아래에서 admin ↔ 일반을 바꿀 수 있습니다.

## 자주 쓰는 명령

```powershell
.venv\Scripts\python.exe -m pytest                     # 백엔드 테스트
cd frontend; npm run build                              # 프런트 타입 검사 + 빌드
.venv\Scripts\python.exe -m src.seed --reset            # 샘플 데이터 다시 넣기
.venv\Scripts\python.exe -m src.knowledge.index         # 컨설팅 문서 다시 색인
.venv\Scripts\python.exe -m src.monitoring.generator --reset   # 샘플 호출 로그 다시 만들기
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "설명"   # 모델 변경 후 마이그레이션
```

## 주요 설정 (`.env`)

| 항목 | 기본값 | 설명 |
|---|---|---|
| `APP_ENV` | `development` | `development`가 아니면 개발용 권한 스위치가 꺼진다 |
| `DATABASE_URL` | `sqlite:///./a2x.db` | PostgreSQL로 바꿀 수 있게 방언 전용 SQL을 쓰지 않는다 |
| `ANTHROPIC_API_KEY` | (비어 있음) | 비우면 Agent가 규칙 기반으로 답한다(검색 · 판정은 LLM 없이 동작) |
| `ANTHROPIC_DEFAULT_MODEL` / `ANTHROPIC_FALLBACK_MODEL` | `claude-sonnet-5-5` / `claude-haiku-5-5` | 장애 시 대체 모델로 전환 |
| `GOOGLE_CLIENT_ID` · `GOOGLE_CLIENT_SECRET` · `GOOGLE_REDIRECT_URI` | | Google 로그인(콘솔에 리디렉션 URI 등록 필요) |
| `CONVERTER_PUBLIC_URL` | `http://localhost:8100` | A2X MCP 런타임 주소 |
| `MASTER_MCP_URL` · `IRP_MCP_URL` · `DCM_MCP_URL` | 8200의 각 경로 | 외부 시스템 MCP |
| `A2X_UPSTREAM_TOKEN_<시스템코드>` | | 런타임이 원본 API를 부를 때 쓰는 토큰 |

전체 목록과 기본값은 [src/shared/config.py](src/shared/config.py)에 있습니다.

## 폴더

```
src/            백엔드(도메인별 폴더: auth · systems · catalog · subscriptions · converter · monitoring · knowledge · agents · tools · audit · shared)
tests/          백엔드 테스트(pytest)
alembic/        DB 마이그레이션
frontend/       React 포탈(src/pages 화면, src/lib/api.ts · queries.ts API 호출)
```

파일 배치 규칙은 CLAUDE.md의 'src 폴더 구조와 파일 배치 규칙'을 따릅니다.
