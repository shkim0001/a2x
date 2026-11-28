"""T2-5 컨설팅 문서 관리: 업로드(원본 바이트) → 추출 → 색인, 다시 색인, 삭제, 검색 시험. 해시 임베딩 · 임시 업로드 폴더."""

import io
import zipfile
from urllib.parse import quote

import pytest

from src.knowledge.extract import extract_text, ExtractError
from src.knowledge.router import get_doc_store
from src.knowledge.service import reindex_all
from src.knowledge.store import HashEmbedder, VectorStore
from src.main import app
from src.shared.config import ROOT_DIR, settings

MD = "# 메시지 큐 연계 가이드\n\n## 1. 카프카 토픽\n\n카프카 토픽 이름은 시스템코드.업무.이벤트 형식으로 짓는다. 파티션은 최소 3개로 둔다.\n"


def docx_bytes() -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    xml = (f'<w:document {w}><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>배치 연계 기준</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>배치 파일은 </w:t></w:r><w:r><w:t>SFTP로 전송한다.</w:t></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>항목</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>기준</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
           '</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def pdf_bytes(pages: list[str]) -> bytes:
    """글자가 들어 있는 최소 PDF(Helvetica, 영문)를 직접 만든다."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{x:010d} 00000 n \n".encode() for x in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_extract_pdf_pages_and_rejections():
    from pypdf import PdfWriter

    text = extract_text("guide.pdf", pdf_bytes(["Kafka topic naming rule", "Consumer group per system"]))
    assert text == "## p.1\n\nKafka topic naming rule\n\n## p.2\n\nConsumer group per system"

    def written(w):
        buf = io.BytesIO()
        w.write(buf)
        return buf.getvalue()

    blank = PdfWriter()
    blank.add_blank_page(612, 792)
    with pytest.raises(ExtractError, match="스캔"):
        extract_text("scan.pdf", written(blank))
    locked = PdfWriter()
    locked.add_blank_page(612, 792)
    locked.encrypt("pw")
    with pytest.raises(ExtractError, match="암호"):
        extract_text("locked.pdf", written(locked))


@pytest.fixture()
def store():
    return VectorStore(in_memory=True, embedder=HashEmbedder())


@pytest.fixture()
def api(client, as_user, store, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.1)  # 해시 임베딩용
    app.dependency_overrides[get_doc_store] = lambda: store
    admin = as_user("admin@example.com")

    def upload(name, data, headers=admin):
        return client.post(f"/api/v1/consult-docs?filename={quote(name)}", content=data, headers={**headers, "Content-Type": "application/octet-stream"})

    yield client, admin, upload
    app.dependency_overrides.pop(get_doc_store, None)


def test_extract_formats():
    assert extract_text("a.md", MD.encode("utf-8-sig")).startswith("# 메시지 큐")
    assert extract_text("a.txt", "가나다".encode("cp949")) == "가나다"
    text = extract_text("a.docx", docx_bytes())
    assert text.startswith("# 배치 연계 기준") and "배치 파일은 SFTP로 전송한다." in text and "항목 | 기준" in text
    for name, data in (("a.pdf", b"%PDF-broken"), ("a.hwp", b"x"), ("a.md", b"   ")):
        with pytest.raises(ExtractError):
            extract_text(name, data)


def test_upload_index_search_delete(api, store, tmp_path):
    client, admin, upload = api
    r = upload("메시지 큐 연계 가이드.md", MD.encode())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "INDEXED" and d["chunk_count"] >= 1 and d["size_bytes"] == len(MD.encode()) and not d["is_sample"]
    assert (tmp_path / "consult_docs" / f"{d['id']}_메시지 큐 연계 가이드.md").is_file()

    s = client.get("/api/v1/consult-docs/search?q=카프카 토픽 이름은 어떻게 짓나요", headers=admin).json()
    assert s["ok"] and s["hits"][0]["doc"] == "메시지 큐 연계 가이드" and "카프카" in s["keywords"]

    names = [x["name"] for x in client.get("/api/v1/consult-docs", headers=admin).json()]
    assert names[0] == "메시지 큐 연계 가이드.md" and "방화벽 신청 절차.md" in names  # 최신순 + 시드 샘플

    assert client.delete(f"/api/v1/consult-docs/{d['id']}", headers=admin).status_code == 204
    assert not any((tmp_path / "consult_docs").iterdir()) and store.count() == 0


def test_docx_upload(api):
    _, _, upload = api
    d = upload("배치 연계 기준.docx", docx_bytes()).json()
    assert d["status"] == "INDEXED" and d["chunk_count"] >= 1


def test_pdf_upload_shows_page_in_sources(api):
    client, admin, upload = api
    d = upload("kafka guide.pdf", pdf_bytes(["Kafka topic naming rule system code event", "Consumer group per subscribing system"])).json()
    assert d["status"] == "INDEXED" and d["chunk_count"] == 2
    s = client.get("/api/v1/consult-docs/search?q=Kafka topic naming rule", headers=admin).json()
    assert s["hits"][0]["doc"] == "kafka guide" and s["hits"][0]["section"] == "p.1"


def test_upload_rejections(api, as_user):
    client, admin, upload = api
    assert upload("a.pdf", b"%PDF-1.7").json()["code"] == "unsupported_doc"  # 깨진 PDF
    assert upload("a.hwp", b"x").json()["code"] == "unsupported_doc"
    assert upload("a.md", b"").status_code == 422
    assert upload("dup.md", MD.encode()).status_code == 201
    assert upload("dup.md", MD.encode()).status_code == 409
    assert upload("x.md", MD.encode(), headers=as_user("hong@example.com")).status_code == 403
    assert client.get("/api/v1/consult-docs", headers=as_user("kim@example.com")).status_code == 403


def test_path_traversal_name_is_sanitized(api, tmp_path):
    _, _, upload = api
    d = upload("../../evil.md", MD.encode()).json()
    assert d["name"] == "evil.md" and (tmp_path / "consult_docs" / f"{d['id']}_evil.md").is_file()


def test_sample_reindex_and_delete_keeps_source(api, store):
    client, admin, _ = api
    sample = next(x for x in client.get("/api/v1/consult-docs", headers=admin).json() if x["name"] == "방화벽 신청 절차.md")
    assert sample["is_sample"] and sample["status"] == "INDEXING"  # 시드는 색인 전
    r = client.post(f"/api/v1/consult-docs/{sample['id']}/reindex", headers=admin).json()
    assert r["status"] == "INDEXED" and r["chunk_count"] >= 1
    assert client.delete(f"/api/v1/consult-docs/{sample['id']}", headers=admin).status_code == 204
    assert (ROOT_DIR / "src/knowledge/sample_docs/firewall-request.md").is_file()  # 원본 샘플 파일은 남는다


def test_index_failure_is_recorded(api, store, monkeypatch):
    _, _, upload = api

    def boom(*a, **k):
        raise RuntimeError("임베딩 모델 없음")

    monkeypatch.setattr(store, "index_document", boom)
    d = upload("실패.md", MD.encode()).json()
    assert d["status"] == "FAILED" and "임베딩 모델 없음" in d["error"] and d["chunk_count"] == 0


def test_reindex_all_clears_stale_chunks(seeded, store):
    store.index_document("sample:old", "지워진 문서", "예전 내용")
    counts = reindex_all(seeded, store)
    assert set(counts) == {"사내 시스템 연계 표준 가이드 v3.md", "MCP 서버 개발 가이드.md", "API 보안 체크리스트.md", "방화벽 신청 절차.md", "A2X 포탈 사용 가이드.md"}
    assert all(v >= 1 for v in counts.values())
    assert "지워진 문서" not in {h.doc_name for h in store.search("예전 내용", k=50)}
