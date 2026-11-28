"""API 레이아웃 엑셀(xlsx) 파싱.

첫 시트에서 머리글 행(필드명/타입/필수/설명)을 찾아 그 아래 행을 필드 목록으로 읽는다.
열 이름 판정과 값 변환은 규칙 코드로 한다.
"""

from io import BytesIO

from openpyxl import load_workbook

# 머리글 별칭 → 표준 키
HEADER_ALIASES = {
    "name": {"필드명", "필드", "항목명", "name", "field"},
    "type": {"타입", "유형", "데이터타입", "type"},
    "required": {"필수", "필수여부", "필수(y/n)", "required"},
    "description": {"설명", "비고", "description", "desc"},
}
VALID_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}
TRUE_VALUES = {"y", "yes", "true", "1", "필수", "o"}
MAX_HEADER_SCAN_ROWS = 10


class LayoutExcelError(ValueError):
    pass


def _norm(v: object) -> str:
    return str(v).strip().lower().replace(" ", "") if v is not None else ""


def _find_header(rows: list[tuple]) -> tuple[int, dict[str, int]]:
    for idx, row in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        cols: dict[str, int] = {}
        for ci, cell in enumerate(row):
            key = _norm(cell)
            for std, aliases in HEADER_ALIASES.items():
                if key in aliases and std not in cols:
                    cols[std] = ci
        if "name" in cols:
            return idx, cols
    raise LayoutExcelError("머리글 행을 찾지 못했습니다. '필드명' 열이 필요합니다.")


def parse_layout_xlsx(data: bytes) -> list[dict]:
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # openpyxl은 형식 오류마다 다른 예외를 낸다
        raise LayoutExcelError("xlsx 파일을 읽을 수 없습니다.") from e

    rows = [tuple(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    wb.close()
    header_idx, cols = _find_header(rows)

    def cell(row: tuple, key: str) -> object:
        ci = cols.get(key)
        return row[ci] if ci is not None and ci < len(row) else None

    fields = []
    for row in rows[header_idx + 1 :]:
        name = cell(row, "name")
        if name is None or str(name).strip() == "":
            continue
        typ = _norm(cell(row, "type")) or "string"
        fields.append(
            {
                "name": str(name).strip(),
                "type": typ if typ in VALID_TYPES else "string",
                "required": _norm(cell(row, "required")) in TRUE_VALUES,
                "description": str(cell(row, "description") or "").strip(),
            }
        )
    return fields
