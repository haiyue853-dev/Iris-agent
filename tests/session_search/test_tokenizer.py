from iris_agent.session_search.models import SearchHit
from iris_agent.session_search.tokenizer import tokenize


def test_tokenize_chinese_bigrams_and_english_words():
    tokens = tokenize("聊聊项目 Python")
    assert "聊聊" in tokens
    assert "项目" in tokens
    assert "python" in tokens


def test_tokenize_is_case_insensitive_and_dedupes():
    assert tokenize("Hello hello") == {"hello"}


def test_tokenize_single_chinese_character():
    tokens = tokenize("好")
    assert "好" in tokens


def test_search_hit_truncates_long_content():
    hit = SearchHit("session_x", "会话", "user", "长" * 400, 1.0, 5)
    assert len(hit.to_dict()["content"]) <= 300


def test_search_hit_dict_has_whitelisted_fields():
    hit = SearchHit("session_x", "会话", "user", "内容", 1.0, 5)
    data = hit.to_dict()
    assert set(data) == {"session_id", "session_name", "role", "content", "updated_at", "score"}
