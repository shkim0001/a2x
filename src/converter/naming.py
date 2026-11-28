"""API 오퍼레이션 → MCP Tool 정의 규칙 (LLM이 아니라 규칙 코드).

프런트엔드 frontend/src/lib/convert.ts 의 toolName 규칙과 같다.
    GET /orders                     → list_orders
    GET /orders/{orderId}           → get_order
    GET /orders/{orderId}/shipments → list_order_shipments
    POST /orders/{orderId}/cancel   → cancel_order
    GET /customers/search           → search_customers
    POST /outbounds                 → create_outbound
"""

import re
from typing import Any

from src.catalog.models import ApiLayoutField, ApiOperation, HttpMethod, LayoutDirection, ToolKind

ACTION_WORDS = {"search", "cancel", "approve", "reject", "confirm"}
VERB = {HttpMethod.POST: "create", HttpMethod.PUT: "update", HttpMethod.PATCH: "update", HttpMethod.DELETE: "delete"}
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
JSON_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}


def _is_param(seg: str) -> bool:
    return seg.startswith("{") and seg.endswith("}")


def _singular(w: str) -> str:
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def path_params(path: str) -> list[str]:
    return [s[1:-1] for s in path.split("/") if _is_param(s)]


def tool_name(method: HttpMethod, path: str) -> str:
    segs = [s for s in path.split("/") if s]
    ends_with_param = bool(segs) and _is_param(segs[-1])
    statics = [s for s in segs if not _is_param(s)]

    if statics and statics[-1] in ACTION_WORDS:
        verb = statics[-1]
        statics = statics[:-1]
    elif method == HttpMethod.GET:
        verb = "get" if ends_with_param else "list"
    else:
        verb = VERB[method]

    words = []
    for i, w in enumerate(statics):
        idx = segs.index(w)
        followed_by_param = idx + 1 < len(segs) and _is_param(segs[idx + 1])
        last = i == len(statics) - 1
        words.append(_singular(w) if followed_by_param or (last and verb not in ("list", "search")) else w)
    name = "_".join([verb, *words]).replace("-", "_").lower()
    return name[:64]


def tool_kind(method: HttpMethod) -> ToolKind:
    return ToolKind.READ if method == HttpMethod.GET else ToolKind.WRITE


def default_description(op: ApiOperation) -> str:
    base = op.summary or f"{op.method.value} {op.path}"
    return f"{base}. " + ("읽기 전용." if op.method == HttpMethod.GET else "데이터를 변경하므로 사용자 확인 후 호출한다.")


def input_schema(op: ApiOperation, layout: list[ApiLayoutField] | None = None) -> dict[str, Any]:
    """경로 파라미터는 필수 문자열, 요청 레이아웃의 최상위 필드는 GET이면 쿼리, 그 외에는 본문 속성."""
    props: dict[str, Any] = {}
    required: list[str] = []
    for p in path_params(op.path):
        props[p] = {"type": "string", "description": f"경로 파라미터 {p}"}
        required.append(p)
    for f in layout or []:
        if f.direction != LayoutDirection.REQUEST or "." in f.name or "[" in f.name or f.name in props:
            continue
        props[f.name] = {"type": f.type if f.type in JSON_TYPES else "string", **({"description": f.description} if f.description else {})}
        if f.required:
            required.append(f.name)
    return {"type": "object", "properties": props, "required": required}


def suggest(op: ApiOperation, layout: list[ApiLayoutField] | None = None) -> dict[str, Any]:
    return {
        "operation_id": op.id,
        "method": op.method.value,
        "path": op.path,
        "tool_name": tool_name(op.method, op.path),
        "description": default_description(op),
        "kind": tool_kind(op.method).value,
        "input_schema": input_schema(op, layout),
    }
