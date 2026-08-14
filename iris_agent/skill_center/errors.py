"""Skill 中心领域错误。"""


class SkillError(Exception):
    """Skill 中心基础错误。"""


class SkillNotFoundError(SkillError):
    """请求的 Skill ID 不存在或非法。"""


class SkillDisabledError(SkillError):
    """请求的 Skill 当前未启用。"""


class SkillValidationError(SkillError):
    """Skill 定义元数据不合法。"""
