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
