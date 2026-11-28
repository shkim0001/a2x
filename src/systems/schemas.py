"""기준정보(시스템 · 서버) 입출력 스키마."""

from pydantic import BaseModel, Field

from src.auth.schemas import UserBrief
from src.shared.schema import Schema
from src.systems.models import DataLevel, ServerEnv, SystemKind


class ServerIn(BaseModel):
    hostname: str = Field(min_length=1, max_length=100)
    ip: str = Field(min_length=1, max_length=45)
    port: int = Field(ge=1, le=65535)
    env: ServerEnv = ServerEnv.PROD
    role: str = Field(default="", max_length=50)


class ServerOut(Schema):
    id: int
    system_id: int
    hostname: str
    ip: str
    port: int
    env: ServerEnv
    role: str


class SystemIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    kind: SystemKind
    process: str = Field(min_length=1, max_length=30)
    dept: str = Field(default="", max_length=100)
    url: str = Field(default="", max_length=500)
    data_level: DataLevel = DataLevel.INTERNAL
    description: str = ""
    manager_emails: list[str] = []  # 등록자 외 추가 담당자
    servers: list[ServerIn] = []


class SystemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    process: str | None = Field(default=None, min_length=1, max_length=30)
    dept: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    data_level: DataLevel | None = None
    description: str | None = None


class SystemOut(Schema):
    id: int
    code: str
    name: str
    kind: SystemKind
    process: str
    dept: str
    url: str
    data_level: DataLevel
    description: str
    managers: list[UserBrief]
    servers: list[ServerOut]


class ServerRow(ServerOut):
    system_code: str
    system_name: str
    process: str


class ManagerIn(BaseModel):
    email: str = Field(max_length=255)


class SystemBrief(Schema):
    id: int
    code: str
    name: str
    dept: str
    kind: SystemKind
