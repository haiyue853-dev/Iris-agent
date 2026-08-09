"""Skills API 请求/响应模型。"""

from pydantic import BaseModel, StrictBool


class SkillInfoModel(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    entry_view: str
    version: int
    enabled: bool


class SkillEnabledRequest(BaseModel):
    enabled: StrictBool
