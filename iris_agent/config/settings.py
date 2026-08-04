from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml

from iris_agent.core.errors import ConfigurationError


@dataclass(slots=True)
class LLMSettings:
    provider: str = "openai_compatible"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    temperature: float = 0.2
    timeout_seconds: float = 60.0


@dataclass(slots=True)
class AgentSettings:
    system_prompt: str = "你是 Iris Agent，一个智能助手。始终使用中文与用户交流。"
    max_tool_rounds: int = 8


@dataclass(slots=True)
class SessionSettings:
    directory: Path = Path("data/sessions")


@dataclass(slots=True)
class ToolSettings:
    enabled: list[str] = field(default_factory=lambda: ["current_time", "list_directory", "read_file"])
    workspace_root: Path = Path("workspace")
    max_read_chars: int = 20_000


@dataclass(slots=True)
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)
    sessions: SessionSettings = field(default_factory=SessionSettings)
    tools: ToolSettings = field(default_factory=ToolSettings)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigurationError(f"配置节 {name} 必须是对象")
    return value


def load_settings(config_path: str | Path = "agent.yaml", **overrides: Any) -> Settings:
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"无法读取配置文件: {exc}") from exc
    llm = _section(raw, "llm")
    agent = _section(raw, "agent")
    sessions = _section(raw, "sessions")
    tools = _section(raw, "tools")
    model = overrides.get("model") or os.getenv("LLM_MODEL") or llm.get("model", "deepseek-chat")
    base_url = overrides.get("base_url") or os.getenv("OPENAI_BASE_URL") or llm.get("base_url", "https://api.deepseek.com/v1")
    api_key = overrides.get("api_key") or os.getenv("OPENAI_API_KEY", "")
    settings = Settings(
        llm=LLMSettings(
            provider=str(llm.get("provider", "openai_compatible")), model=str(model),
            base_url=str(base_url), api_key=str(api_key),
            temperature=float(llm.get("temperature", 0.2)), timeout_seconds=float(llm.get("timeout_seconds", 60)),
        ),
        agent=AgentSettings(system_prompt=str(agent.get("system_prompt", raw.get("system_prompt", AgentSettings().system_prompt))), max_tool_rounds=int(agent.get("max_tool_rounds", 8))),
        sessions=SessionSettings(directory=Path(sessions.get("directory", raw.get("session_path", "data/sessions")))),
        tools=ToolSettings(enabled=list(tools.get("enabled", ToolSettings().enabled)), workspace_root=Path(tools.get("workspace_root", "workspace")), max_read_chars=int(tools.get("max_read_chars", 20_000))),
    )
    if not settings.llm.model.strip() or settings.agent.max_tool_rounds < 1:
        raise ConfigurationError("模型名称不能为空，且 max_tool_rounds 必须大于 0")
    return settings
