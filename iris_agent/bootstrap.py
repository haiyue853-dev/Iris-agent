from pathlib import Path

from openai import OpenAI

from iris_agent.config.settings import Settings, load_settings
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.builtin import build_current_time_tool, build_list_directory_tool, build_read_file_tool
from iris_agent.tools.registry import ToolRegistry


def build_application(config_path: str | Path = "agent.yaml"):
    settings = load_settings(config_path)
    client = OpenAI(api_key=settings.llm.api_key or "missing", base_url=settings.llm.base_url, timeout=settings.llm.timeout_seconds)
    provider = OpenAICompatibleProvider(client, settings.llm.model, settings.llm.temperature)
    registry = ToolRegistry()
    factories = {
        "current_time": lambda: build_current_time_tool(),
        "list_directory": lambda: build_list_directory_tool(settings.tools.workspace_root),
        "read_file": lambda: build_read_file_tool(settings.tools.workspace_root, settings.tools.max_read_chars),
    }
    settings.tools.workspace_root.mkdir(parents=True, exist_ok=True)
    for name in settings.tools.enabled:
        if name in factories:
            registry.register(factories[name]())
    sessions = JsonSessionRepository(settings.sessions.directory)
    loop = AgentLoop(provider, registry, settings.agent.max_tool_rounds)
    return AgentService(loop, sessions, settings.agent.system_prompt), sessions, settings
