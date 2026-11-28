# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 상태

1차 작업(TASKS.md) 완료. 백엔드는 `src/` 아래 도메인별 구조(아래 'src 폴더 구조와 파일 배치 규칙').
- `src/`: 백엔드 Python 코드 전체(FastAPI 포탈 API, A2X Agent, API→MCP 컨버터, 모의 마스터 MCP). import는 `src.<도메인>...` 절대 경로. 설정은 루트 `.env`.
- `tests/`: 백엔드 테스트(pytest, 루트에서 실행). `alembic/` · `alembic.ini`: DB 마이그레이션. `requirements.txt`: 백엔드 의존성.
- `frontend/`: React 포탈. 화면은 `src/pages/`, API 호출은 `src/lib/api.ts`(fetch + 응답 타입) · `src/lib/queries.ts`(TanStack Query 훅), 코드값 → 한글 표시는 `src/lib/labels.ts`. 포탈 화면은 모두 백엔드 API에 연결됨(`src/lib/sample-data.ts`는 타입 · 화면 상수 일부만). 모니터링은 `/monitoring/*` API(호출 로그는 1차 샘플 생성기 데이터). 규칙 코드: `src/lib/convert.ts`(API→MCP Tool 이름, 백엔드 `src/converter/naming.py`와 같은 규칙), `src/lib/layout-import.ts`(Swagger/JSON/CSV 레이아웃).

## 문서 역할

- **README.md**: 처음 보는 개발자용 소개 · 실행 방법(프로세스 4개 · 계정 · 주요 설정).
- **SERVICE.md**: 무엇을 만드는지(목적, 모듈 M1~M5, 흐름, 요구사항). 기준 문서이며 애매하면 추측하지 말고 물어본다.
- **CLAUDE.md**(이 파일): 어떻게 개발하는지(스택, 작업 규칙, 명령어, 아키텍처).
- **TASKS.md**: 작업 목록. 한 번에 하나씩 진행한다.
- **AGENTS.md**: A2X Agent(M5) 설계 문서(Supervisor 라우팅 규칙, 업무 Agent별 역할 · Tool, 모의 MCP Tool 목록, 가드레일, 평가 방법). Agent 작업 전에 읽는다.
- **HISTORY.md**: 작업 이력. 아래 작업 규칙에 따라 갱신한다.
- **ref/**: 참조 코드 폴더. 아직 없음.

## 기술 스택

- Python, LangGraph, WSO2(Gateway 계층)
- LLM: Claude API(Anthropic SDK)를 직접 사용한다. 모델은 환경 설정으로 지정하며, 장애나 상황에 따라 복수 모델을 전환해 중단 없이 쓸 수 있게 설계한다. 기본 모델은 `claude-sonnet-5-5`, 장애 시 대체 모델은 `claude-haiku-5-5`(`.env`의 `ANTHROPIC_DEFAULT_MODEL` / `ANTHROPIC_FALLBACK_MODEL`).
- Agent: LangGraph 멀티 Agent. Supervisor는 규칙 기반 라우팅(Python 코드)이다. 컨설팅 Agent는 RAG + ChromaDB를 쓴다. 외부 마스터는 MCP Tool로 읽어 포탈 입력란을 자동 채운다. 1차에서는 모의 MCP 서버를 쓴다.
- 인증: Google 인증(OAuth/OIDC)과 자체 사용자 가입(즉시 가입)을 모두 지원한다. 사내 IdP로 교체 가능하게 인증 계층을 분리한다.
- DB: SQLite로 시작하며 PostgreSQL 전환 가능성이 있다. DB 종류에 종속된 코드(방언 전용 SQL 등)를 피하고 접근 계층을 분리한다.
- 멀티테넌시: 1차에는 넣지 않는다(추후 개발). 테넌트 관련 코드를 미리 만들지 않는다.
- Control plane(포탈, 거버넌스, Agent)과 Data plane(Gateway)을 코드와 배포 단위에서 분리한다. Gateway 계층은 WSO2에 직접 묶지 말고 추상화한다.
- 1차 개발은 웹 포탈과 A2X Agent 중심이다. Gateway(WSO2)는 후순위다. 단계는 SERVICE.md 참고.
- 웹 프런트엔드: React + TypeScript + Vite, Tailwind CSS + shadcn/ui, TanStack Query.

### 라이브러리 승인 현황

새 라이브러리는 이 목록에서 "승인"인 것만 쓴다. 목록에 없으면 먼저 묻는다.

| 용도 | 라이브러리 | 상태 |
|---|---|---|
| Agent | LangGraph | 승인 |
| LLM | Anthropic SDK (`anthropic`) | 승인 |
| 벡터 DB | ChromaDB | 승인 |
| 프런트엔드 | React, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query | 승인 |
| 백엔드 웹 프레임워크 | FastAPI (uvicorn) | 승인 |
| DB 접근 / 마이그레이션 | SQLAlchemy, Alembic | 승인 |
| 모의 MCP 서버 / MCP 클라이언트 | 공식 MCP Python SDK (`mcp`) | 승인 |
| Google 인증 | Authlib | 승인 |
| 비밀번호 해시 | bcrypt | 승인 |
| 임베딩 모델 (ChromaDB용) | sentence-transformers (ChromaDB 기본/로컬) | 승인 |
| 설정 / 환경변수 (백엔드) | pydantic-settings, python-dotenv | 승인 |
| HTTP 클라이언트 (백엔드, FastAPI TestClient 포함) | httpx | 승인 |
| 테스트 (백엔드) | pytest | 승인 |
| 엑셀(xlsx) 파싱 (백엔드) | openpyxl | 승인 |
| PDF 텍스트 추출 (백엔드, 컨설팅 문서) | pypdf | 승인 |
| YAML 파서 (프런트엔드, Swagger import) | yaml (npm) | 승인 |
| shadcn/ui 부속 | @radix-ui/*, class-variance-authority, clsx, tailwind-merge, lucide-react | 승인 |

## 작업 규칙

- 한 번에 `TASKS.md`의 작업 하나만 한다.
- 레퍼런스: GitHub의 괜찮은 레퍼런스 코드를 찾아 참고하거나, `ref/` 폴더의 코드를 참조한다.
- 사용자 허락 없이 신규 프레임워크/라이브러리를 도입하지 않는다.
- 계산과 규칙 판정은 LLM이 아니라 Python 코드로 한다. 필요하면 LLM 판정을 그 위에 덧붙인다.
- API 키 등 비밀 값은 `.env`에서 읽는다.
- 파일을 만들거나 바꾸는 작업, 또는 사용자 결정이 나온 대화가 끝나면 `HISTORY.md` 맨 아래에 항목을 추가한다. 날짜 제목 아래 번호를 이어서 붙이고, 무엇을 했는지와 결정된 내용을 한두 줄로 적는다. 남은 결정 목록도 최신으로 고친다.

## 개발 명령어

- Python 가상환경: `.venv` (Python 3.13.3). 시스템 PATH의 `python`은 Microsoft Store 바로가기라 동작하지 않으므로, `.venv`의 Python을 직접 실행하거나 경로를 지정해 사용한다.
  - 활성화(PowerShell): `.venv\Scripts\Activate.ps1`
  - 활성화 없이 실행: `.venv\Scripts\python.exe ...`
모든 명령은 저장소 루트에서 실행한다.
- 백엔드 실행: `.venv\Scripts\python.exe -m uvicorn src.main:app --reload --reload-dir src --port 8000`
- 백엔드 테스트: `.venv\Scripts\python.exe -m pytest` / 단일 테스트: `... -m pytest tests/test_main.py::test_health`
- DB 마이그레이션: `.venv\Scripts\python.exe -m alembic upgrade head` / 모델 변경 후 `... -m alembic revision --autogenerate -m "설명"`(새 도메인 모델은 `src/models.py`에 등록해야 감지된다). `alembic.ini`는 Windows 기본 인코딩으로 읽히므로 한글을 넣지 않는다.
- 샘플 데이터: `.venv\Scripts\python.exe -m src.seed` (다시 넣기: `--reset`). DB 파일과 `.env`는 실행 위치와 상관없이 저장소 루트 기준.
- 모니터링 샘플 호출 로그(시드 명령이 함께 실행): `.venv\Scripts\python.exe -m src.monitoring.generator` (다시 만들기: `--reset`, 기간: `--days 60`). 컨버터의 실제 호출 로그(`CV-`)는 지우지 않는다.
- A2X MCP 런타임(컨버터 · 중계, 포탈과 별도 프로세스): `.venv\Scripts\python.exe -m uvicorn src.converter.server:app --port 8100` → `http://localhost:8100/mcp/{자산ID}`(변환 MCP는 원본 API로, 직접 개발 MCP는 원본 MCP로 중계). Agent의 시스템 · 서버 자동 채움도 이 중계를 거치므로 함께 띄운다. 호출 헤더 `X-A2X-User`(이메일) · `X-A2X-Subscription`(시스템 구독 ID). 원본 API 토큰은 `.env`의 `A2X_UPSTREAM_TOKEN_<시스템코드>`.
- 모의 외부 시스템 MCP 서버(Agent 자동 채움용, 한 프로세스): `.venv\Scripts\python.exe -m uvicorn src.tools.mock_master.server:app --port 8200` → 마스터 `http://localhost:8200/mcp` · IRP(시스템 마스터) `/irp/mcp` · DCM(서버 자산) `/dcm/mcp`. 주소는 설정 `MASTER_MCP_URL` · `IRP_MCP_URL` · `DCM_MCP_URL`.
- 컨설팅 문서 다시 색인(DB에 등록된 문서 전체, 임베딩 모델 첫 실행 시 내려받기): `.venv\Scripts\python.exe -m src.knowledge.index` → `chroma_data/`. 시드 명령도 끝에 색인한다. 문서 추가 · 삭제는 포탈 '관리 › 컨설팅 문서'(admin), 업로드 파일은 `uploads/`. 근거 판정 보정 테스트는 `A2X_REAL_EMBEDDING=1`일 때만 실제 모델로 돈다.
- 개발용 권한 스위치: 오른쪽 위 사용자 이름 아래에서 admin ↔ 일반을 바꾼다(`PUT /api/v1/auth/dev/role`, `USER` · `ADMIN`). `APP_ENV=development`일 때만 켜지고(`DEV_ROLE_SWITCH`로 강제 가능), 운영에서는 403. 시스템 담당자는 저장하는 역할이 아니라 담당 시스템이 있으면 자동으로 된다(시스템을 등록하거나 담당자로 추가되면).
- 개발용 로그인(시드): `hong@example.com`(시스템 담당자) · `admin@example.com` · `kim@example.com` · `lee@example.com`(담당 시스템 없음), 비밀번호 `a2x-demo-1234`. 그 밖의 시드 담당자(예: `hwang.sangki@example.com`, `kim.heeryeong@example.com`)도 같은 비밀번호. 시스템 이름은 시스템 코드(영문 약어)와 같다. 검색은 이름 · 코드 · 부서 · 업무 프로세스로.
- 프런트엔드(`frontend/`, Node 20.15라 Vite 6 고정): `npm install`, `npm run dev`(5173, `/api`는 8000으로 프록시), `npm run build`(타입 검사 포함)
- 린트는 정해지면 추가한다.

## src 폴더 구조와 파일 배치 규칙

백엔드 코드는 기술 역할(models · services 등)이 아니라 **도메인(기능) 단위**로 나눈다. 한 기능을 고칠 때 한 폴더 안에서 끝나게 하는 것이 목적이다.

### 폴더 역할

| 폴더 | 도메인 | 담는 것 |
|---|---|---|
| `src/main.py` · `api.py` · `models.py` · `seed.py` | 조립(composition root) | 앱 생성 · `/api/v1` 라우터 모음 · 전체 모델 등록 · 개발용 샘플 데이터. 도메인 로직을 두지 않는다 |
| `src/shared/` | 공용 유틸리티 | `config.py`(설정 · 루트 경로) · `errors.py`(서비스 오류) · `llm.py`(LLM 클라이언트, 모델 전환) · `trace.py`(실행 흐름 기록) · `schema.py`(스키마 기반 클래스) · `db/`(Base · 세션 · 저장소 기반 클래스). **도메인 코드를 import하지 않는다** |
| `src/auth/` | 인증 | 사용자 · 로그인 세션 모델, 자체 가입 · 로그인, Google 로그인(`google.py`), 비밀번호 해시(`security.py`), 현재 사용자 확인(`deps.py`), 사용자 검색(`users_router.py`, 담당자 지정용 · 로그인한 사용자 누구나, 이름 · 이메일만) |
| `src/systems/` | 기준정보 | 시스템 · 담당자 · 서버, 역할 · 담당자 권한 판정(`access.py`) |
| `src/catalog/` | 카탈로그 | API · MCP 자산 등록 · 수정 · 진행상태(저장→승인→스테이지→운영) · 노출 범위, 레이아웃 가져오기(`layout_excel.py`, `layout_router.py`) |
| `src/subscriptions/` | 구독 | 2단계 구독(시스템 구독 · 사용자 Tool 신청) · 승인 · 해지, 호출 시점 권한 판정(`is_tool_permitted`) |
| `src/converter/` | API→MCP 변환 | 변환 설계 규칙(`naming.py`) · 변환 생성(`service.py`) · 변환 MCP 런타임(`runtime.py` · `server.py`, 별도 프로세스) |
| `src/monitoring/` | 모니터링 | 호출 로그 모델, 조회 범위 · 오류 분류 · 통계(`service.py`), 샘플 호출 로그 생성기(`generator.py`) |
| `src/knowledge/` | 지식(컨설팅 문서 · RAG) | 문서 관리, 텍스트 추출(`extract.py`), ChromaDB 색인 · 검색(`store.py`), 근거 판정(`evidence.py`), 샘플 문서(`sample_docs/`) |
| `src/agents/` | A2X Agent(M5) | LangGraph 그래프(`graph.py`) · 상태(`state.py`) · 규칙 Supervisor(`supervisor.py`) · 가드레일(`guard.py`) · 채팅 API, 업무 Agent별 하위 폴더(`consult/` · `automation/` · `devsupport/` · `error_action/`) |
| `src/tools/` | Agent Tool | 포탈 내부 Tool(`portal.py`, 읽기 전용) · 외부 마스터 MCP 클라이언트(`master_client.py`) · 모의 마스터 MCP 서버(`mock_master/`) |
| `src/audit/` | 감사 | 감사 로그 모델 · 기록 |

### 도메인 폴더 안의 파일 이름

| 파일 | 내용 |
|---|---|
| `models.py` | SQLAlchemy 모델과 그 도메인의 코드값(Enum) |
| `schemas.py` | API 입출력 스키마(Pydantic). 라우터 안에 스키마를 두지 않는다 |
| `repository.py` | 조회(SQL) — 반복되는 조회 조건만 메서드로 |
| `service.py` | 규칙 판정 · 상태 전이 · 감사 기록. SQL을 직접 쓰지 않는다 |
| `router.py` | FastAPI 라우터: 입력 검증 · 스키마 변환 · 커밋만. 규칙을 두지 않는다. 같은 도메인의 두 번째 라우터는 `<이름>_router.py` |
| `prompts.py` | LLM 시스템 프롬프트(고정 문자열, 캐시 대상). 프롬프트를 로직 파일에 섞지 않는다 |
| `agent.py` | 업무 Agent 실행 로직(`async run(...) -> AgentResult`) |
| 그 밖 | 도메인 고유 모듈은 하는 일을 이름으로(예: `evidence.py`, `templates.py`, `generator.py`) |

### 배치 규칙

- 새 기능은 먼저 어느 도메인인지 정하고 그 폴더 안에 둔다. 기존 도메인에 맞지 않으면 새 도메인 폴더를 만들고, 라우터는 `src/api.py`, 모델은 `src/models.py`에 한 줄 등록한다.
- 업무 Agent를 추가하면 `src/agents/<이름>/`(`agent.py` · 필요하면 `prompts.py` · `templates.py`)를 만들고 `graph.py`의 노드와 `supervisor.py`의 라우팅 규칙을 고친다.
- 모델(`models.py`)끼리의 참조는 한 방향만: `auth` ← `systems` ← `catalog` ← `subscriptions`(`monitoring` · `knowledge` · `audit`는 외래 키 이름으로만 참조). 모델 사이 순환 import를 만들지 않는다.
- 서비스 · 라우터는 다른 도메인의 `service` · `repository` · `models` · `schemas`를 import해 쓸 수 있다. 규칙은 그 규칙을 가진 도메인의 service 함수를 불러 쓰고 복사하지 않는다(예: 노출 범위는 `catalog.service`, 조회 범위는 `monitoring.service`).
- `agents`는 `tools` · `knowledge` 등을 쓰지만, 다른 도메인은 `agents`를 import하지 않는다. `tools`는 각 도메인의 service를 읽기 전용으로만 쓴다(쓰기 Tool 없음).
- `shared/`에는 둘 이상의 도메인이 쓰는 기술 유틸리티만 둔다(LLM 클라이언트 · 설정 · DB 기반 · 오류). 특정 도메인 규칙은 넣지 않는다.
- 테스트는 루트 `tests/test_<도메인 또는 기능>.py`.

## 아키텍처

여러 파일을 읽어야 파악되는 큰 그림만 적는다.

- **계층(도메인 폴더 안)**: `router.py`(입출력 · 커밋) → `service.py`(규칙 판정 · 상태 전이 · 감사 로그) → `repository.py`(조회) → `models.py`(SQLAlchemy). 서비스 오류(`shared/errors.py`)는 `{detail, code}` JSON이 된다.
- **권한 판정 지점**: `systems/access.py`(저장 역할은 admin · 일반뿐. 화면 역할 `effective_role`은 admin이 아니면 담당 시스템이 있을 때 시스템 담당자로 계산해 메뉴 · 버튼에만 쓴다. 실제 관리 · 승인 권한은 그 시스템의 담당자인가로 판정. 시스템 등록은 누구나, 등록한 사람이 첫 담당자) · `catalog/service.py`(자산 진행상태 전이 표, 수정 가능 상태, 노출 범위) · `subscriptions/service.py`(2단계 구독 승인권자 = 프로바이더 시스템 담당자 또는 admin(모든 시스템, 감사 로그에 `as_admin`), 호출 시점 판정 `is_tool_permitted`).
- **모니터링**: `monitoring/service.py`가 조회 범위(admin 전체 / 그 외 담당 시스템이 클라이언트 · 프로바이더인 호출 + 내 호출) · 오류 분류 규칙 · 일별/월별 집계(Python, DB 방언 함수 없음)를 갖고, 화면(`monitoring/router.py`)과 오류 조치 Agent가 같이 쓴다. 사용내역 `/monitoring/calls`는 페이지 단위(`page` · `size` ≤ 200 → `{items, total}`)이고 조건 · 검색어는 모두 DB에서 거른다(`CallLogRepository._filtered`). 기간은 `days`(최근 N일) 또는 `start` · `end`(시간대 없으면 KST, 최대 366일, `monitoring.service.period`), 통계 `/monitoring/stats`는 `start` · `end` 날짜(일별 최대 366일 · 월별 최대 36개월). 인스턴스 모니터링 `/monitoring/instances`(시스템 담당자 · admin)는 `monitoring/health.py`가 구성요소(포탈 · 권한 Gateway · MCP/API Gateway · MCP 서버 · 외부 MCP · Agent · 운영 데이터)를 점검해 ok · warn · down · off로 판정한다(10초 캐시, 예시 도메인 `.example` 주소는 점검 제외, MCP 엔드포인트는 ping으로). 런타임(8100)은 `GET /health`를 제공한다. 화면 페이지 이동은 공용 `components/pager.tsx`. 시각은 UTC로 저장 · 비교하고 표시는 KST.
- **동기 작업과 async**: async 엔드포인트 · Agent 노드 안의 무거운 동기 작업(임베딩 검색 · 색인, LLM 호출)은 `run_in_threadpool` / `anyio.to_thread`로 돌린다(이벤트 루프를 막으면 서버 전체가 멈춘다).
- **Control plane / Data plane**: 포탈 API(`src.main`, 8000)와 A2X MCP 런타임(`src.converter.server`, 8100)은 별도 프로세스다. 런타임은 변환 MCP의 `tools/call`을 원본 API HTTP 호출로 바꾸고 직접 개발 MCP는 원본 MCP로 그대로 중계하며, 호출마다 `is_tool_permitted`로 권한을 집행한 뒤 `call_logs`에 남긴다. 3차 Gateway 도입 시 이 모듈을 Gateway 계층으로 옮긴다.
- **A2X Agent**: `POST /api/v1/agent/chat` → `agents/service.py`(로그인 사용자 문맥 · 감사 로그) → `agents/graph.py`(LangGraph: pre_guard → 규칙 Supervisor → 업무 Agent 하나 → post_guard). 업무 Agent는 `agents/<이름>/agent.py`, 포탈 조회는 `tools/portal.py`(서비스 계층 그대로, 쓰기 없음), 외부 마스터는 MCP(`tools/master_client.py`, 1차 모의 서버 8200), 가드레일은 `agents/guard.py`. LLM이 없으면 규칙 기반으로 답한다. 실행 흐름(`shared/trace.py`, contextvars): 그래프 노드 · 포탈 Tool · MCP 호출 · RAG 검색 · 근거 판정 · LLM 호출이 '누가 → 누구에게 · 무엇을 · 결과 · ms'를 남기고 채팅 응답의 `trace`로 돌려준다. 화면은 `components/agent-flow.tsx`가 시퀀스 다이어그램으로 그린다. 새 Tool · 단계를 만들면 `trace.span` / `trace.step`으로 기록하고, detail에는 비밀 값 · 개인정보를 넣지 않는다(개수 · 이름 · 요약만).
- **인증**: DB 세션 토큰(`auth_sessions`, 해시 저장), HttpOnly 쿠키 또는 Bearer. Google 로그인(`auth/google.py`)은 OAuth 2.0 + PKCE(Authlib httpx 클라이언트), state · verifier는 서명 쿠키, 사용자 정보는 userinfo 엔드포인트, 계정 연결 규칙은 sub → 같은 이메일 연결 → 즉시 가입. 로그인 후 세션은 자체 로그인과 같다. 사내 IdP로 바꿀 때는 `auth/google.py`(엔드포인트 · 클레임 매핑)와 `auth/deps.py`의 사용자 확인만 바꾼다.
- **프런트엔드**: 로그인 확인(`App.tsx`의 `useMe`) 후 포탈을 연다. 역할은 서버가 계산한 `effective_role`을 쓰고, 버튼 표시는 서버가 준 `can_decide` · `can_cancel`을 따른다(화면에서 권한을 다시 판정하지 않음). 변경 후에는 `useAction`이 목록 쿼리를 모두 새로고친다. Agent 패널(`components/agent-panel.tsx`)과 화면은 `lib/agent-bridge.tsx`(Context)로 연결된다: 화면 문맥(`setFocus`), 화면에서 질문 보내기(`ask`), 양식 제안 적용(`useSuggestion(form, fn)` — 값만 채우고 제출은 사용자). 개발 중 `/api`는 Vite 프록시로 같은 출처가 되어 HttpOnly 쿠키로 인증된다.
