import json

from iris_agent.interview_knowledge.collector import InterviewCollectionService
from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository


def _result(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class FakeMcp:
    def __init__(self) -> None:
        self.calls = []

    def call_tool(self, server_id, name, arguments):
        self.calls.append((server_id, name, arguments))
        if name == "search_interview_sources":
            return _result({"results": [
                {"url": "https://one.example/questions", "title": "Python Interview"},
                {"url": "https://two.example/questions", "title": "More Python Questions"},
            ]})
        if arguments["url"].startswith("https://one"):
            return _result({"items": [
                {"question": "What is the GIL?", "answer": "The GIL permits one thread to execute Python bytecode at a time.", "source_url": arguments["url"]},
                {"question": "What is a tuple?", "answer": "A tuple is an immutable ordered collection of values.", "source_url": arguments["url"]},
            ]})
        return _result({"items": [
            {"question": "What   is a tuple?", "answer": "Duplicate answer that should not be returned.", "source_url": arguments["url"]},
            {"question": "What is a decorator?", "answer": "A decorator wraps a callable to extend its behavior.", "source_url": arguments["url"]},
        ]})


def test_preview_collects_and_deduplicates_without_saving(tmp_path):
    repository = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    repository.save("Python", [{"question": "What is the GIL?", "answer": "Existing answer", "source_url": "https://existing.example"}])
    mcp = FakeMcp()
    collector = InterviewCollectionService(mcp, repository)

    preview = collector.preview("Python", max_sources=2, max_items_per_source=5)

    assert [item["question"] for item in preview["items"]] == ["What is a tuple?", "What is a decorator?"]
    assert preview["summary"] == {"sources": 2, "found": 2, "duplicates": 2}
    assert len(repository.list("Python")) == 1


def test_save_requires_explicit_call_after_preview(tmp_path):
    repository = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    collector = InterviewCollectionService(FakeMcp(), repository)
    preview = collector.preview("Python", max_sources=1)

    result = collector.save("Python", preview["items"])

    assert result == {"added": 2, "total": 2}
