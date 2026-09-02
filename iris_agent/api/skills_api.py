"""Skills 中心 API：只暴露公开元数据与启用状态，不返回路径或可执行内容。"""

import logging

from fastapi import HTTPException

from iris_agent.api.skills_schemas import (
    SkillEnabledRequest,
    SkillInfoModel,
    UserSkillContentModel,
    UserSkillSaveRequest,
)
from iris_agent.skill_center.errors import SkillNotFoundError
from iris_agent.skill_center.models import SkillInfo

logger = logging.getLogger(__name__)


def _to_model(info: SkillInfo) -> SkillInfoModel:
    return SkillInfoModel(
        id=info.id,
        name=info.name,
        description=info.description,
        icon=info.icon,
        category=info.category,
        entry_view=info.entry_view,
        version=info.version,
        enabled=info.enabled,
        source=info.source,
        allowed_toolsets=list(info.allowed_toolsets),
    )


def register_skills_routes(app, skills):
    """注册 Skills 中心路由（需要 SkillCenterService 实例）。"""

    @app.get("/api/skills")
    def list_skills():
        return {"skills": [_to_model(item).model_dump() for item in skills.list_skills()]}

    @app.post("/api/skills/user", status_code=201)
    def save_user_skill(request: UserSkillSaveRequest):
        try:
            definition = skills.save_user_skill(request.name, request.description, request.content, tuple(request.allowed_toolsets))
            return _to_model(skills.get_skill(definition.id)).model_dump()
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_user_skill", "message": str(exc)},
            ) from exc

    @app.get("/api/skills/{skill_id}/content")
    def get_user_skill_content(skill_id: str):
        try:
            definition = skills.load_user_skill(skill_id)
            metadata = _to_model(skills.get_skill(skill_id))
            return UserSkillContentModel(**metadata.model_dump(), content=definition.body).model_dump()
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "skill_not_found", "message": "未找到该 Skill"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=403, detail={"code": "bundled_skill_readonly", "message": str(exc)}) from exc

    @app.delete("/api/skills/user/{skill_id}", status_code=204)
    def delete_user_skill(skill_id: str):
        try:
            skills.delete_user_skill(skill_id)
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "skill_not_found", "message": "未找到该 Skill"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=403, detail={"code": "bundled_skill_readonly", "message": str(exc)}) from exc

    @app.get("/api/skills/{skill_id}")
    def get_skill(skill_id: str):
        try:
            return _to_model(skills.get_skill(skill_id)).model_dump()
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "skill_not_found", "message": "未找到该 Skill"}) from exc

    @app.put("/api/skills/{skill_id}/enabled")
    def set_skill_enabled(skill_id: str, request: SkillEnabledRequest):
        try:
            return _to_model(skills.set_enabled(skill_id, request.enabled)).model_dump()
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "skill_not_found", "message": "未找到该 Skill"}) from exc
