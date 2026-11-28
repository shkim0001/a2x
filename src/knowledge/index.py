"""컨설팅 문서 색인.

실행(저장소 루트에서): .venv\\Scripts\\python.exe -m src.knowledge.index
→ DB에 등록된 컨설팅 문서(샘플 포함)를 모두 다시 색인한다(벡터 저장소를 비우고 시작).
문서 추가 · 삭제는 포탈의 '관리 › 컨설팅 문서'(admin)에서 한다.
"""

from pathlib import Path

from src.knowledge.store import VectorStore, get_store

SAMPLE_DIR = Path(__file__).parent / "sample_docs"

# 테스트용: DB 없이 샘플 문서를 바로 색인한다(파일 → 문서명)
SAMPLE_DOCS = {
    "integration-standard-v3.md": "사내 시스템 연계 표준 가이드 v3",
    "mcp-server-dev-guide.md": "MCP 서버 개발 가이드",
    "api-security-checklist.md": "API 보안 체크리스트",
    "firewall-request.md": "방화벽 신청 절차",
    "portal-guide.md": "A2X 포탈 사용 가이드",
}


def index_samples(store: VectorStore) -> dict[str, int]:
    return {name: store.index_document(f"sample:{fname}", name, (SAMPLE_DIR / fname).read_text(encoding="utf-8")) for fname, name in SAMPLE_DOCS.items()}


if __name__ == "__main__":
    from src.shared.db.session import SessionLocal
    from src.knowledge.service import reindex_all

    with SessionLocal() as db:
        counts = reindex_all(db, get_store())
        db.commit()
    print("색인 완료:", ", ".join(f"{k} {v}청크" for k, v in counts.items()) or "등록된 문서 없음")
