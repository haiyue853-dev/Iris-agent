from dataclasses import dataclass

from iris_agent.knowledge.orchestrator import KnowledgeOrchestrator
from iris_agent.memory.models import MemoryEntry
from iris_agent.session_search.models import SearchHit


class FakeRag:
    def __init__(self):
        self.calls = []

    def context_for(self, query, collection_id=None, mode="mix"):
        self.calls.append((query, collection_id, mode))
        return (
            "[本地知识库综合检索结果]\n[1] 《Iris 方案》\n统一知识检索编排器",
            [
                {
                    "index": 1,
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "title": "Iris 方案",
                    "content": "统一知识检索编排器",
                    "score": 0.9,
                }
            ],
        )


class FakeMemory:
    def list(self):
        return [
            MemoryEntry.new("Iris 下一步实现统一知识检索编排器", "project", entry_id="memory-1"),
            MemoryEntry.new("用户喜欢简洁回答", "preference", entry_id="memory-2"),
        ]


class FakeSessionSearch:
    def __init__(self):
        self.queries = []

    def search(self, query, limit=None):
        self.queries.append(query)
        return [
            SearchHit("session-2", "架构讨论", "assistant", "统一知识检索编排器", 10.0, 3),
            SearchHit("session-3", "重复讨论", "user", "统一知识检索编排器", 9.0, 2),
        ]


@dataclass
class FakeMessage:
    role: str
    content: str


class FakeSessions:
    def get(self, session_id):
        return type(
            "FakeSession",
            (),
            {"messages": [FakeMessage("user", "Iris 的统一知识检索编排器怎么设计？")]},
        )()


def make_orchestrator():
    rag = FakeRag()
    return KnowledgeOrchestrator(
        rag=rag,
        memory=FakeMemory(),
        session_search=FakeSessionSearch(),
        sessions=FakeSessions(),
        max_context_chars=4000,
    ), rag


def test_plan_routes_global_questions_to_graph_context():
    orchestrator, _ = make_orchestrator()

    plan = orchestrator.plan("总结这些资料的整体主题和冲突")

    assert plan.rag_mode == "global"
    assert "graph" in plan.routes
    assert "整体主题" in plan.high_level_keywords


def test_context_rewrites_vague_question_from_recent_user_turn():
    orchestrator, rag = make_orchestrator()

    context, _ = orchestrator.context_for("这个怎么实现？", "session-1", "collection-1", "mix")

    rewritten_query, collection_id, _ = rag.calls[0]
    assert rewritten_query == "Iris 的统一知识检索编排器怎么设计？ 这个怎么实现？"
    assert collection_id == "collection-1"
    assert "[知识检索计划]" in context


def test_context_rewrites_follow_up_about_the_retrieved_sources():
    orchestrator, rag = make_orchestrator()

    orchestrator.context_for("基于这些资料，下一步可以怎么做？", "session-1", "collection-1", "mix")

    rewritten_query, _, _ = rag.calls[0]
    assert rewritten_query == "Iris 的统一知识检索编排器怎么设计？ 基于这些资料，下一步可以怎么做？"


def test_retrieve_deduplicates_content_and_assigns_unified_citations():
    orchestrator, _ = make_orchestrator()

    _, citations = orchestrator.context_for("统一知识检索编排器", "session-1", None, "mix")

    assert [item["index"] for item in citations] == list(range(1, len(citations) + 1))
    assert {item["source_type"] for item in citations} >= {"document", "memory"}
    duplicate_text = [item for item in citations if item.get("content") == "统一知识检索编排器"]
    assert len(duplicate_text) == 1
