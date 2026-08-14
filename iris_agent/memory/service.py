from iris_agent.memory.models import MemoryItem
from iris_agent.memory.provider import MemoryProvider


class MemoryService:
    def __init__(self, provider: MemoryProvider, max_results: int = 4) -> None:
        self.provider = provider
        self.max_results = max_results

    def remember(self, content: str, session_id: str | None = None, tags: tuple[str, ...] = ()) -> MemoryItem:
        return self.provider.remember(content, session_id, tags)

    def search(self, query: str, session_id: str | None = None) -> list[MemoryItem]:
        return self.provider.search(query, session_id, self.max_results)

    def list(self, session_id: str | None = None) -> list[MemoryItem]:
        return self.provider.list(session_id)

    def delete(self, memory_id: str) -> None:
        self.provider.delete(memory_id)

    def context_for(self, query: str, session_id: str) -> str:
        memories = self.search(query, session_id)
        if not memories:
            return ""
        lines = [f"- {item.content[:500]}" for item in memories]
        return "Relevant saved memories:\n" + "\n".join(lines)
