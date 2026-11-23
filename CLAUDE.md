# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 상태

저장소가 비어 있는 초기 단계다. 코드가 생기면 실제 구조와 명령어에 맞게 갱신할 것.

## 문서 역할

- **SERVICE.md**: 무엇을 만드는지(목적, 모듈 M1~M5, 흐름, 요구사항). 기준 문서이며 애매하면 추측하지 말고 물어본다.
- **CLAUDE.md**(이 파일): 어떻게 개발하는지(스택, 작업 규칙, 명령어, 아키텍처).
- **TASKS.md**: 작업 목록. 한 번에 하나씩 진행한다.
- **HISTORY.md**: 작업 이력. 아래 작업 규칙에 따라 갱신한다.
- **ref/**: 참조 코드 폴더. 아직 없음.

## 기술 스택

- Python, LangGraph, WSO2(Gateway 계층)
- LLM: Claude API(Anthropic SDK)를 직접 사용한다. 모델은 환경 설정으로 지정하며, 장애나 상황에 따라 복수 모델을 전환해 중단 없이 쓸 수 있게 설계한다. 기본 모델 ID는 `[결정 필요]`.
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
| 백엔드 웹 프레임워크 | 미정 (예: FastAPI) | 승인 필요 |
| DB 접근 / 마이그레이션 | 미정 (예: SQLAlchemy, Alembic) | 승인 필요 |
| 모의 MCP 서버 / MCP 클라이언트 | 미정 (예: 공식 MCP Python SDK) | 승인 필요 |
| Google 인증 | 미정 (예: Authlib) | 승인 필요 |
| 비밀번호 해시 | 미정 (예: argon2-cffi, bcrypt) | 승인 필요 |
| 임베딩 모델 (ChromaDB용) | 미정 | 승인 필요 |

## 작업 규칙

- 한 번에 `TASKS.md`의 작업 하나만 한다.
- 레퍼런스: GitHub의 괜찮은 레퍼런스 코드를 찾아 참고하거나, `ref/` 폴더의 코드를 참조한다.
- 사용자 허락 없이 신규 프레임워크/라이브러리를 도입하지 않는다.
- 계산과 규칙 판정은 LLM이 아니라 Python 코드로 한다. 필요하면 LLM 판정을 그 위에 덧붙인다.
- API 키 등 비밀 값은 `.env`에서 읽는다.
- 파일을 만들거나 바꾸는 작업, 또는 사용자 결정이 나온 대화가 끝나면 `HISTORY.md` 맨 아래에 항목을 추가한다. 날짜 제목 아래 번호를 이어서 붙이고, 무엇을 했는지와 결정된 내용을 한두 줄로 적는다. 남은 결정 목록도 최신으로 고친다.

## 개발 명령어

- Python 가상환경: `.venv` (Python 3.13.1). 시스템 PATH의 `python`은 Microsoft Store 바로가기라 동작하지 않으므로, `.venv`의 Python을 쓰거나 `py -3.13`을 쓴다.
  - 활성화(PowerShell): `.venv\Scripts\Activate.ps1`
  - 활성화 없이 실행: `.venv\Scripts\python.exe ...`
- 빌드, 린트, 테스트(단일 테스트 실행 방법 포함)는 정해지면 추가한다.

## 아키텍처

미정. 모듈 구조가 잡히면 여러 파일을 읽어야 파악되는 큰 그림(모듈 간 호출 흐름, 권한·가드레일 적용 지점)만 기록한다.
