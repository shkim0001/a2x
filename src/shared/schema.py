"""공용 API 스키마 기반 클래스와 공용 응답."""

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(Schema):
    message: str
