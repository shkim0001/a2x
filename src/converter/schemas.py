"""API → MCP 변환 API 입출력 스키마."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolSuggestion(BaseModel):
    operation_id: int
    method: str
    path: str
    tool_name: str
    description: str
    kind: str
    input_schema: dict[str, Any]


class ConvertToolIn(BaseModel):
    operation_id: int
    name: str | None = Field(default=None, max_length=64)
    description: str | None = None


class ConvertIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = ""
    tools: list[ConvertToolIn] = Field(min_length=1)
    submit: bool = False
