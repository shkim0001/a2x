"""개발 지원 Agent 예시 코드 템플릿(코드로 채운다. 비밀 값은 자리표시만)."""

from __future__ import annotations

import json
import re
from typing import Any

from src.shared.config import settings


def example_args(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not schema:
        return {}
    sample = {"string": lambda n: f"<{n}>", "integer": lambda n: 1, "number": lambda n: 1.0, "boolean": lambda n: True, "array": lambda n: [], "object": lambda n: {}}
    props = schema.get("properties", {})
    names = list(dict.fromkeys([*schema.get("required", []), *list(props)[:3]]))
    return {n: sample.get(props.get(n, {}).get("type", "string"), sample["string"])(n) for n in names if n in props}


def _headers(asset: dict, email: str, sub_id: int | None) -> dict[str, str]:
    if asset["source"] == "MCP_CONVERTED":  # A2X 컨버터: 사용자 · 시스템 구독 헤더로 권한 집행
        return {"X-A2X-User": email, "X-A2X-Subscription": str(sub_id) if sub_id else "<SUBSCRIPTION_ID>"}
    return {"Authorization": "Bearer <YOUR_TOKEN>"}  # 타겟 시스템이 직접 운영하는 서버 · API: 그 시스템의 인증


def mcp_python(asset: dict, tool: dict | None, headers: dict[str, str]) -> str:
    hdr = "\n".join(f'    "{k}": "{v}",' for k, v in headers.items())
    call = (
        f'            result = await client.call_tool("{tool["name"]}", {json.dumps(example_args(tool.get("input_schema")), ensure_ascii=False)})\n'
        "            print(result.structured_content or result.content)\n"
    ) if tool else ""
    return (
        f'"""{asset["name"]} ({asset["system_code"]}) MCP 호출 예시 — pip install mcp"""\n'
        "import asyncio\n\n"
        "import httpx2\n"
        "from mcp.client.client import Client\n"
        "from mcp.client.streamable_http import streamable_http_client\n\n"
        f'URL = "{asset["endpoint"]}"\n'
        f"HEADERS = {{\n{hdr}\n}}\n\n\n"
        "async def main() -> None:\n"
        "    async with httpx2.AsyncClient(headers=HEADERS) as http:\n"
        "        async with Client(streamable_http_client(URL, http_client=http)) as client:\n"
        "            tools = await client.list_tools()\n"
        "            print([t.name for t in tools.tools])\n"
        f"{call}\n\n"
        "asyncio.run(main())\n"
    )


def mcp_curl(asset: dict, tool: dict | None, headers: dict[str, str]) -> str:
    hdr = "".join(f' \\\n  -H "{k}: {v}"' for k, v in headers.items())
    if tool:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool["name"], "arguments": example_args(tool.get("input_schema"))}}
    else:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    return (
        f'curl -s -X POST "{asset["endpoint"]}" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -H "Accept: application/json, text/event-stream"'
        f"{hdr} \\\n"
        f"  -d '{json.dumps(body, ensure_ascii=False)}'\n"
    )


def api_curl(asset: dict, op: dict | None, headers: dict[str, str]) -> str:
    if not op:
        return f'curl -s "{asset["base_url"]}/<PATH>" -H "Authorization: Bearer <YOUR_TOKEN>"\n'
    path = re.sub(r"\{(\w+)\}", r"<\1>", op["path"])
    hdr = "".join(f' \\\n  -H "{k}: {v}"' for k, v in headers.items())
    body = f' \\\n  -H "Content-Type: {asset["content_type"]}" \\\n  -d \'{{}}\'' if op["method"] in ("POST", "PUT", "PATCH") else ""
    return f'curl -s -X {op["method"]} "{asset["base_url"]}{path}"{hdr}{body}\n'


def api_python(asset: dict, op: dict | None, headers: dict[str, str]) -> str:
    method, path = (op["method"], re.sub(r"\{(\w+)\}", r"<\1>", op["path"])) if op else ("GET", "/<PATH>")
    body = ", json={}" if method in ("POST", "PUT", "PATCH") else ""
    return (
        f'"""{asset["name"]} ({asset["system_code"]}) API 호출 예시 — pip install httpx"""\n'
        "import httpx\n\n"
        f'BASE_URL = "{asset["base_url"]}"\n'
        f"HEADERS = {json.dumps(headers, ensure_ascii=False)}\n\n"
        f'resp = httpx.request("{method}", f"{{BASE_URL}}{path}", headers=HEADERS{body}, timeout=10)\n'
        "resp.raise_for_status()\n"
        "print(resp.json())\n"
    )


def portal_curl(email: str, sub_id: int | None, tool: str | None) -> str:
    base = settings.PORTAL_PUBLIC_URL.rstrip("/")
    sub = sub_id or "<SUBSCRIPTION_ID>"
    return (
        "# 1) 로그인 → 응답의 token 값을 <YOUR_TOKEN>에 넣는다\n"
        f'curl -s -X POST "{base}/api/v1/auth/login" -H "Content-Type: application/json" \\\n'
        f"  -d '{{\"email\": \"{email}\", \"password\": \"<YOUR_PASSWORD>\"}}'\n\n"
        "# 2) 카탈로그 검색(운영 상태)\n"
        f'curl -s "{base}/api/v1/assets?status=LIVE&q=<검색어>" -H "Authorization: Bearer <YOUR_TOKEN>"\n\n'
        "# 3) 이 연계에서 Tool을 호출할 수 있는지 확인\n"
        f'curl -s "{base}/api/v1/permissions/check?subscription_id={sub}&tool={tool or "<TOOL_NAME>"}" -H "Authorization: Bearer <YOUR_TOKEN>"\n'
    )
