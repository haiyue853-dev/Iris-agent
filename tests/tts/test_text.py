from iris_agent.tts.text import speech_text_from_markdown


def test_speech_text_keeps_readable_content_and_omits_code_and_link_targets() -> None:
    markdown = """# 结论

请看 [官方文档](https://example.com)，然后继续。

```python
print("不要朗读")
```

**今天**也请多关照。
"""

    assert speech_text_from_markdown(markdown) == (
        "结论\n请看 官方文档，然后继续。\n今天也请多关照。"
    )


def test_speech_text_removes_characters_that_crash_gpt_sovits_gbk_logging() -> None:
    assert speech_text_from_markdown("你好😊，继续🚀。\n高松燈です。") == (
        "你好，继续。\n高松燈です。"
    )
