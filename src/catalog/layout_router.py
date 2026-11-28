from fastapi import APIRouter, HTTPException, Request

from src.catalog.layout_excel import LayoutExcelError, parse_layout_xlsx

router = APIRouter(prefix="/layout", tags=["layout"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.post("/excel")
async def parse_excel(request: Request):
    """xlsx 파일을 요청 본문(application/octet-stream)으로 받아 레이아웃 필드 목록을 돌려준다.

    multipart 처리 라이브러리(python-multipart)는 미승인이라 원본 바이트를 그대로 받는다.
    """
    data = await request.body()
    if not data:
        raise HTTPException(400, "파일이 비어 있습니다.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "파일은 5MB 이하여야 합니다.")
    try:
        return {"fields": parse_layout_xlsx(data)}
    except LayoutExcelError as e:
        raise HTTPException(422, str(e)) from e
