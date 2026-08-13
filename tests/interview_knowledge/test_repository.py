from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository


def test_repository_keeps_complete_unique_question_answer_pairs(tmp_path):
    repository = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    assert repository.save("Python", [{"question": "什么是 GIL？", "answer": "解释器锁", "source_url": "https://example.com"}]) == {"added": 1, "total": 1}
    assert repository.save("python", [{"question": "什么是 GIL？", "answer": "其他答案", "source_url": "https://example.com"}]) == {"added": 0, "total": 1}
