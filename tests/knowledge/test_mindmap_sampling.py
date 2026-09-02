from iris_agent.knowledge.mindmap import select_mindmap_chunks


def test_mindmap_sampling_covers_the_whole_document():
    chunks = [type("Chunk", (), {"id": f"chunk-{index}", "ordinal": index, "content": str(index)})() for index in range(100)]

    selected = select_mindmap_chunks(chunks, limit=24)

    assert len(selected) == 24
    assert selected[0].ordinal == 0
    assert selected[-1].ordinal == 99
    assert any(45 <= item.ordinal <= 55 for item in selected)
