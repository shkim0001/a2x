"""인증 도메인 입출력 스키마."""

from datetime import datetime
from typing import Literal

from src.shared.schema import Schema

from pydantic import BaseModel, Field


class UserOut(Schema):
    id: int
    email: str
    name: str
    role: str
    auth_provider: str
    created_at: datetime | None = None


class UserBrief(Schema):
    id: int
    name: str
    email: str


class SignupIn(BaseModel):
    email: str = Field(max_length=255)
    name: str = Field(max_length=100)
    password: str = Field(max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class SessionOut(BaseModel):
    user: UserOut
    effective_role: str
    token: str  # 쿠키를 못 쓰는 클라이언트용(Authorization: Bearer)


class MeOut(BaseModel):
    user: UserOut
    effective_role: str
    managed_system_ids: list[int]


class ProvidersOut(BaseModel):
    google: bool
    dev_role_switch: bool = False  # 개발용 권한 스위치를 보여 줄지


class RoleSwitchIn(BaseModel):
    role: Literal["USER", "ADMIN"]  # 시스템 담당자는 담당 시스템 유무로 계산되므로 바꾸는 대상이 아니다
