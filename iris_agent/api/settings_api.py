"""AI 配置设置 API

提供读取与更新 LLM 配置（API Key / Base URL / Model）的能力：
  GET /api/settings           → 当前配置状态（key 只显示掩码与是否已设置）
  PUT /api/settings           → 保存配置到 .env 并动态更新运行中的模型客户端（立即生效）

说明：
- API Key 写入项目根目录 .env（OPENAI_API_KEY 等），服务重启后仍生效。
- 保存时同步更新内存中的 OpenAI client（api_key/base_url）与 provider（model），无需重启。
- 前端只能读取掩码后的 key，无法获取明文。
"""
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # iris_agent/api/.. -> 项目根
ENV_FILE = PROJECT_ROOT / ".env"


def _mask_key(key: str) -> str:
    """掩码显示：sk-****abcd"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}****{key[-4:]}"


def _read_env() -> dict[str, str]:
    """读取 .env 为 dict（保留注释，只取 KEY=VALUE）"""
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _write_env(updates: dict[str, str]) -> None:
    """更新 .env 中指定 KEY 的值（保留注释与其它行）；新增不存在的 KEY"""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    keys = set(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in keys:
                out.append(f"{key}={updates.pop(key)}")
                continue
        out.append(line)
    # 追加剩余新增项
    for key, value in updates.items():
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def _current_state(service) -> dict:
    """从运行中的服务读取当前配置状态（掩码 key）"""
    provider = service.loop.provider
    client = getattr(provider, "client", None)
    api_key = getattr(client, "api_key", "") if client else ""
    base_url = str(getattr(client, "base_url", "")) if client else ""
    return {
        "model": getattr(provider, "model", ""),
        "base_url": base_url,
        "api_key_set": bool(api_key),
        "api_key_masked": _mask_key(str(api_key)),
    }


class SettingsUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)


def register_settings_routes(app, service):
    """在 create_app 中注册设置路由（需要访问运行中的 service）"""

    @app.get("/api/settings")
    def get_settings():
        return _current_state(service)

    @app.put("/api/settings")
    def put_settings(payload: SettingsUpdate):
        try:
            # 1) 读取当前 .env，合并更新
            env = _read_env()
            if payload.api_key is not None:
                env["OPENAI_API_KEY"] = payload.api_key.strip()
            if payload.base_url is not None:
                env["OPENAI_BASE_URL"] = payload.base_url.strip()
            if payload.model is not None:
                env["LLM_MODEL"] = payload.model.strip()
            _write_env(env)

            # 2) 动态更新运行中的 client / provider（立即生效，无需重启）
            provider = service.loop.provider
            client = getattr(provider, "client", None)
            if client is not None:
                if payload.api_key is not None and payload.api_key.strip():
                    client.api_key = payload.api_key.strip()
                if payload.base_url is not None and payload.base_url.strip():
                    client.base_url = payload.base_url.strip()
            if payload.model is not None and payload.model.strip():
                provider.model = payload.model.strip()

            return _current_state(service)
        except Exception as exc:
            logger.exception("保存设置失败")
            raise HTTPException(status_code=500, detail={"code": "settings_save_failed", "message": "保存设置失败，请检查 .env 权限"}) from exc
