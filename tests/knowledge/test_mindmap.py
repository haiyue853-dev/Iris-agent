from iris_agent.knowledge.chunker import ChunkDraft
from iris_agent.knowledge.documents import KnowledgeDocument
from iris_agent.knowledge.mindmap import MindMapNode, normalise_mindmap_payload
from iris_agent.knowledge.sqlite_repository import SqliteKnowledgeRepository


def _document():
    return KnowledgeDocument(
        id="doc-0123456789abcdef0123456789abcdef",
        title="Iris 知识库设计",
        source_type="manual",
        media_type="text/plain",
        size_bytes=100,
        original_name=None,
        status="ready",
        error_message=None,
        created_at=1000.0,
        updated_at=1000.0,
    )


def test_normalise_mindmap_builds_one_bounded_three_level_tree():
    chunks = [
        type("Chunk", (), {"id": "chunk-1", "ordinal": 0})(),
        type("Chunk", (), {"id": "chunk-2", "ordinal": 1})(),
    ]
    payload = {
        "summary": "全文介绍 Iris 的知识组织与检索方式。",
        "branches": [
            {
                "title": "知识组织",
                "summary": "把资料组织成结构化知识。",
                "evidence_ordinals": [0],
                "children": [
                    {"title": "文档思维导图", "summary": "生成全文层级摘要。", "evidence_ordinals": [0]},
                    {"title": "跨资料关系图", "summary": "连接不同资料里的实体。", "evidence_ordinals": [1]},
                ],
            }
        ],
    }

    nodes = normalise_mindmap_payload("Iris 知识库设计", payload, chunks)

    assert nodes[0] == MindMapNode("root", None, "Iris 知识库设计", payload["summary"], "root", 0, ())
    assert nodes[1].parent_id == "root"
    assert nodes[2].parent_id == nodes[1].id
    assert nodes[2].evidence_chunk_ids == ("chunk-1",)
    assert len(nodes) <= 40
    assert all(len(node.label) <= 20 for node in nodes if node.kind != "root")


def test_repository_replaces_and_reads_document_mindmap(tmp_path):
    repository = SqliteKnowledgeRepository(tmp_path / "knowledge.db")
    document = _document()
    repository.save_document_with_chunks(document, [ChunkDraft("知识组织正文", None)])
    nodes = [
        MindMapNode("root", None, document.title, "全文总结", "root", 0, ()),
        MindMapNode("branch-1", "root", "知识组织", "主题总结", "branch", 0, ()),
        MindMapNode("point-1-1", "branch-1", "文档思维导图", "关键观点", "point", 0, ()),
    ]

    repository.replace_document_mindmap(document.id, nodes)

    assert repository.document_mindmap(document.id) == nodes
    repository.replace_document_mindmap(document.id, nodes[:2])
    assert repository.document_mindmap(document.id) == nodes[:2]
