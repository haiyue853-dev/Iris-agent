"""Skills API 请求/响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field, StrictBool

SkillToolset = Literal["safe", "research", "coding", "knowledge", "skills", "delegation"]


class SkillInfoModel(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    entry_view: str
    version: int
    enabled: bool
    source: str
    allowed_toolsets: list[SkillToolset] = Field(default_factory=list)


class SkillEnabledRequest(BaseModel):
    enabled: StrictBool


class UserSkillSaveRequest(BaseModel):
    name: str
    description: str
    content: str
    allowed_toolsets: list[SkillToolset] = Field(default_factory=list)


class UserSkillContentModel(SkillInfoModel):
    content: str
