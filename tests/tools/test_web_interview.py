from iris_agent.tools.builtin.web_interview import extract_qa_pairs


def test_extract_qa_pairs_keeps_only_labeled_pairs():
    html = "<p>网页介绍</p><p>问题：什么是 GIL？</p><p>答案：解释器全局锁。</p><p>Q: 什么是生成器？</p><p>A: 惰性迭代器。</p>"
    assert extract_qa_pairs(html, "https://example.com") == [
        {"question": "什么是 GIL？", "answer": "解释器全局锁。", "source_url": "https://example.com"},
        {"question": "什么是生成器？", "answer": "惰性迭代器。", "source_url": "https://example.com"},
    ]
