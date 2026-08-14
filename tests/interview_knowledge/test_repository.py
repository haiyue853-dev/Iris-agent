from iris_agent.interview_knowledge.repository import InterviewKnowledgeRepository


def test_repository_keeps_complete_unique_question_answer_pairs(tmp_path):
    repository = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    assert repository.save("Python", [{"question": "什么是 GIL？", "answer": "解释器锁", "source_url": "https://example.com"}]) == {"added": 1, "total": 1}
    assert repository.save("python", [{"question": "什么是 GIL？", "answer": "其他答案", "source_url": "https://example.com"}]) == {"added": 0, "total": 1}


def test_repository_schedules_review_states_and_supports_legacy_items(tmp_path):
    repository = InterviewKnowledgeRepository(tmp_path / "knowledge.json")
    repository.save("Python", [{"question": "什么是 GIL？", "answer": "解释器锁", "source_url": "https://example.com"}])

    item = repository.next_review(now=100)
    assert item is not None
    assert item["review_state"] == "new"
    updated = repository.mark_reviewed(item["id"], "known", now=100)

    assert updated["next_review_at"] == 100 + 7 * 24 * 60 * 60
    assert repository.next_review(now=101) is None
