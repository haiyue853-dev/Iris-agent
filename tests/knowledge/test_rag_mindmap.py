from iris_agent.knowledge.mindmap import MindMapNode
from iris_agent.knowledge.rag_service import RagKnowledgeService
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository


class MindMapExtractor:
    def outline(self, title, content):
        return [], []

    def extract(self, title, content):
        return [], []

    def mind_map(self, title, chunks):
        return [
            MindMapNode("root", None, title, "全文总结", "root", 0, ()),
            MindMapNode("branch-1", "root", "核心主题", "主题总结", "branch", 0, (chunks[0].id,)),
        ]


def test_rag_service_generates_and_returns_document_mindmap(tmp_path):
    service = RagKnowledgeService(
        SqliteKnowledgeRepository(tmp_path / "knowledge.db"),
        embedder=None,
        files_directory=tmp_path / "files",
        chunk_target_chars=800,
        chunk_overlap_chars=120,
        embedding_batch_size=16,
        retrieval_limit=5,
        max_context_chars=6000,
        minimum_relevance_score=0.2,
        max_file_bytes=10_000_000,
        max_total_bytes=100_000_000,
        max_document_count=100,
        allowed_extensions=(".txt",),
        graph_extractor=MindMapExtractor(),
    )
    try:
        document = service.add_text("Iris 知识库", "全文内容")

        result = service.document_mindmap(document.id)

        assert result["document_id"] == document.id
        assert result["nodes"][0]["kind"] == "root"
        assert result["nodes"][1]["evidence_chunk_ids"]
    finally:
        service.close()


def test_rag_service_persists_and_replays_bad_cases(tmp_path):
    service = RagKnowledgeService(
        SqliteKnowledgeRepository(tmp_path / "knowledge.db"),
        embedder=None,
        files_directory=tmp_path / "files",
        chunk_target_chars=800,
        chunk_overlap_chars=120,
        embedding_batch_size=16,
        retrieval_limit=5,
        max_context_chars=6000,
        minimum_relevance_score=0.2,
        max_file_bytes=10_000_000,
        max_total_bytes=100_000_000,
        max_document_count=100,
        allowed_extensions=(".txt",),
        graph_extractor=MindMapExtractor(),
    )
    try:
        case = service.record_bad_case({"question": "什么是全文内容？", "expected_answer": "全文内容"})

        assert case["id"]
        assert service.list_bad_cases()[0]["question"] == "什么是全文内容？"
        replay = service.replay_bad_case(case["id"])
        assert replay["evaluation"]["total"] == 1
    finally:
        service.close()
