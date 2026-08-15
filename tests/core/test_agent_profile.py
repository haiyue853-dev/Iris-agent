from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.models import ProfilePatch
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class CapturingProvider:
    def __init__(self):
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append(list(messages))
        return ProviderResponse(content="done")


class FakeExtractor:
    def __init__(self, patch: ProfilePatch):
        self.patch = patch
        self.calls = 0

    def extract(self, dialogue: str) -> ProfilePatch:
        self.calls += 1
        return self.patch


def _profile_service(tmp_path, patch: ProfilePatch) -> ProfileService:
    repo = ProfileRepository(tmp_path / "profile")
    return ProfileService(repo, FakeExtractor(patch), extract_interval_rounds=10)


def test_agent_injects_profile_into_system_messages(tmp_path):
    profile_service = _profile_service(tmp_path, ProfilePatch())
    profile_service.apply_patch(ProfilePatch(name="小明"))
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system", profile_service=profile_service)

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents == ["system", "[画像] 称呼：小明"]


def test_agent_injects_no_profile_when_empty(tmp_path):
    profile_service = _profile_service(tmp_path, ProfilePatch())
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system", profile_service=profile_service)

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents == ["system"]


def test_profile_injected_before_memory(tmp_path):
    profile_service = _profile_service(tmp_path, ProfilePatch())
    profile_service.apply_patch(ProfilePatch(facts=["工程师"]))
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    memory.add("用户偏好中文", "preference")
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system", memory=memory, profile_service=profile_service)

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents[0] == "system"
    assert system_contents[1].startswith("[画像]")
    assert system_contents[2].startswith("[记忆·")


def test_run_triggers_profile_extraction(tmp_path):
    profile_service = _profile_service(tmp_path, ProfilePatch(name="小明"))
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system", profile_service=profile_service)

    list(service.run(session.id, "我叫小明"))

    assert profile_service.get().name == "小明"
    assert profile_service.extractor.calls == 1


def test_run_skips_extraction_when_no_profile_service(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    provider = CapturingProvider()
    service = AgentService(AgentLoop(provider, ToolRegistry()), repo, "system")

    list(service.run(session.id, "你好"))

    system_contents = [m.content for m in provider.calls[0] if m.role == "system"]
    assert system_contents == ["system"]
