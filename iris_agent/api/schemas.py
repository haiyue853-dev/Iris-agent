from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


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
