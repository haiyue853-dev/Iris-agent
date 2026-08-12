from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository


def test_repository_stores_complete_unique_questions(tmp_path):
    repository = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    first = repository.save("Python", [{"question": "什么是 GIL？", "answer": "解释器锁", "source_url": "https://example.com"}])
    duplicate = repository.save("python", [{"question": "什么是 GIL？", "answer": "不同答案", "source_url": "https://example.com"}])

    assert first == {"added": 1, "total": 1}
    assert duplicate == {"added": 0, "total": 1}
    assert repository.list("PYTHON")[0]["answer"] == "解释器锁"
