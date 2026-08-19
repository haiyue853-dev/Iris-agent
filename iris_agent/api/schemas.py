from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(default="")
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_message_or_attachment(self):
        if not self.message.strip() and not self.attachment_ids:
            raise ValueError("message or attachment_ids is required")
        return self


class CreateSessionRequest(BaseModel):
    name: str = Field(default="新对话", max_length=100)


class QueueTaskRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ToolApprovalRequest(BaseModel):
    approved: bool


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: Literal["preference", "fact", "project", "other"] = "fact"


class ProfileUpdateRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    preferences: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    style: str = Field(default="", max_length=500)
    facts: list[str] = Field(default_factory=list)


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    category: str = Field(default="面经", max_length=50)
    source_url: str | None = Field(default=None, max_length=2000)


class CuratorApplyRequest(BaseModel):
    suggestion_ids: list[str] | None = None
    all: bool = False
