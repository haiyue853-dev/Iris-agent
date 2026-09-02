from iris_agent.knowledge.mindmap import build_fallback_mindmap


def test_fallback_mindmap_keeps_labels_short_and_hierarchical():
    chunks = [
        type("Chunk", (), {"id": "chunk-1", "ordinal": 0, "content": "# 架构设计\n统一检索负责整合文档、记忆和会话。\n路由器根据问题选择来源。"})(),
        type("Chunk", (), {"id": "chunk-2", "ordinal": 1, "content": "# 引用机制\n所有结果都保留来源编号。"})(),
    ]

    nodes = build_fallback_mindmap("Iris 知识库", chunks)

    assert nodes[0].kind == "root"
    assert {node.label for node in nodes if node.kind == "branch"} == {"架构设计", "引用机制"}
    assert all(node.parent_id is not None for node in nodes[1:])
    assert all(len(node.label) <= 20 for node in nodes[1:])
    assert len(nodes) <= 40
