"""업로드 문서 → 텍스트. 승인된 라이브러리만 쓴다(표준 라이브러리, pypdf).

- .md · .txt: UTF-8(BOM 포함), 안 되면 CP949로 읽는다.
- .docx: zip 안의 word/document.xml에서 문단(w:p)별 글자(w:t)를 모은다. 제목 스타일(Heading/제목)은 마크다운 제목으로 바꿔
  청크의 '절' 이름이 되게 한다. 표는 셀을 ' | '로 잇는다.
- .pdf: pypdf로 쪽마다 글자를 뽑고 '## p.N' 제목을 붙여 근거 출처에 쪽 번호가 나오게 한다.
  암호가 걸린 PDF, 글자가 없는 스캔본(이미지)은 거절한다(OCR 없음).
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

SUPPORTED = (".md", ".txt", ".docx", ".pdf")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ExtractError(Exception):
    pass


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ExtractError("텍스트 인코딩을 읽을 수 없습니다(UTF-8 또는 CP949로 저장해 주세요).")


def _paragraph(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ExtractError("DOCX 파일을 열 수 없습니다.") from e
    body = ET.fromstring(xml).find(f"{W}body")
    if body is None:
        return ""
    lines: list[str] = []
    for el in body:
        if el.tag == f"{W}p":
            text = _paragraph(el).strip()
            if not text:
                continue
            style = el.find(f"{W}pPr/{W}pStyle")
            name = (style.get(f"{W}val") or "") if style is not None else ""
            m = re.search(r"(?:Heading|제목)\s*(\d)", name, re.IGNORECASE)
            lines.append(f"{'#' * min(int(m.group(1)), 3)} {text}" if m else text)
        elif el.tag == f"{W}tbl":
            for row in el.iter(f"{W}tr"):
                cells = [" ".join(_paragraph(p) for p in tc.iter(f"{W}p")).strip() for tc in row.iter(f"{W}tc")]
                if any(cells):
                    lines.append(" | ".join(cells))
    return "\n\n".join(lines)


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractError("암호가 걸린 PDF는 올릴 수 없습니다. 암호를 풀고 올려 주세요.")
        pages = [(i, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages, 1)]
    except ExtractError:
        raise
    except (PdfReadError, ValueError, KeyError) as e:
        raise ExtractError("PDF 파일을 읽을 수 없습니다.") from e
    parts = [f"## p.{i}\n\n{text}" for i, text in pages if text]
    if not parts:
        raise ExtractError("PDF에서 글자를 찾지 못했습니다(스캔한 이미지 PDF는 지원하지 않습니다).")
    return "\n\n".join(parts)


def extract_text(filename: str, data: bytes) -> str:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext in (".md", ".txt"):
        text = _decode(data)
    elif ext == ".docx":
        text = _docx(data)
    elif ext == ".pdf":
        text = _pdf(data)
    else:
        raise ExtractError(f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'}. MD · TXT · DOCX · PDF만 올릴 수 있습니다.")
    text = text.strip()
    if not text:
        raise ExtractError("문서에서 글자를 찾지 못했습니다.")
    return text
