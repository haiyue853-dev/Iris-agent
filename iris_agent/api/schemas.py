from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)
    skill_id: str | None = Field(default=None, max_length=64)


class CreateSessionRequest(BaseModel):
    name: str = Field(default="新对话", max_length=100)
