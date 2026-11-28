from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.main import app

client = TestClient(app)


def make_xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def post(data: bytes):
    return client.post(
        "/api/v1/layout/excel",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def test_parse_layout_with_title_row_and_aliases():
    data = make_xlsx(
        [
            ["주문 API 레이아웃"],  # 머리글 위 제목 행
            ["필드명", "데이터타입", "필수여부", "비고"],
            ["orderId", "string", "Y", "주문 번호"],
            ["qty", "INTEGER", "N", "수량"],
            [None, None, None, None],  # 빈 행은 건너뜀
            ["memo", "text", "", None],  # 알 수 없는 타입은 string
        ]
    )
    res = post(data)
    assert res.status_code == 200
    assert res.json()["fields"] == [
        {"name": "orderId", "type": "string", "required": True, "description": "주문 번호"},
        {"name": "qty", "type": "integer", "required": False, "description": "수량"},
        {"name": "memo", "type": "string", "required": False, "description": ""},
    ]


def test_missing_header_returns_422():
    res = post(make_xlsx([["a", "b"], ["1", "2"]]))
    assert res.status_code == 422


def test_not_xlsx_returns_422():
    res = post(b"not an excel file")
    assert res.status_code == 422


def test_empty_body_returns_400():
    res = post(b"")
    assert res.status_code == 400
