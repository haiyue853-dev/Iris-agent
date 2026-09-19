from datetime import datetime, timedelta, timezone

import pytest

from iris_agent.personal_assistant.classifier import ProviderMessageClassifier, RuleBasedMessageClassifier, parse_chinese_due_at


TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
NOW = datetime(2026, 9, 13, 10, 0, tzinfo=TZ)


def test_date_number_is_not_mistaken_for_an_hour():
    due_at = parse_chinese_due_at("9月15日提醒我提交材料", NOW, default_hour=20)

    assert due_at == datetime(2026, 9, 15, 20, 0, tzinfo=TZ)


def test_rule_classifier_directly_creates_explicit_reminder():
    result = RuleBasedMessageClassifier().classify("提醒我明天下午3点续费服务器", NOW)

    assert result.task is not None
    assert result.task.certainty == "create"
    assert result.task.title == "续费服务器"
    assert result.task.due_at == datetime(2026, 9, 14, 15, 0, tzinfo=TZ)


def test_rule_classifier_asks_before_turning_copied_notice_into_task():
    result = RuleBasedMessageClassifier().classify("通知：请于明天提交材料", NOW)

    assert result.task is not None
    assert result.task.certainty == "confirm"


def test_provider_failure_falls_back_to_rule_classifier():
    class BrokenProvider:
        def complete(self, messages, tools):
            raise RuntimeError("offline")

    classifier = ProviderMessageClassifier(lambda: BrokenProvider())

    result = classifier.classify("提醒我后天上午9点交材料", NOW)

    assert result.task is not None
    assert result.task.certainty == "create"
    assert result.task.due_at == datetime(2026, 9, 15, 9, 0, tzinfo=TZ)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("今天晚上6点提醒我开始背诵面试经验", datetime(2026, 9, 13, 18, 0, tzinfo=TZ)),
        ("今晚6点提醒我背诵", datetime(2026, 9, 13, 18, 0, tzinfo=TZ)),
        ("晚上6点提醒我背诵", datetime(2026, 9, 13, 18, 0, tzinfo=TZ)),
        ("下午6点提醒我背诵", datetime(2026, 9, 13, 18, 0, tzinfo=TZ)),
        ("今天提醒我背诵面试经验", datetime(2026, 9, 13, 20, 0, tzinfo=TZ)),
        ("明天晚上6点提醒我背诵", datetime(2026, 9, 14, 18, 0, tzinfo=TZ)),
        ("明天6点提醒我背诵", datetime(2026, 9, 14, 6, 0, tzinfo=TZ)),
        ("后天下午3点提醒我", datetime(2026, 9, 15, 15, 0, tzinfo=TZ)),
    ],
)
def test_relative_day_and_bare_clock_phrasings_resolve(text, expected):
    """回归 T-001：只给「今天/今晚」或只给钟点，曾被整段丢掉并回退到 +2 天默认时间。"""
    assert parse_chinese_due_at(text, NOW, default_hour=20) == expected


def test_a_clock_time_already_passed_today_rolls_over_to_tomorrow():
    assert parse_chinese_due_at("今天早上9点提醒我", NOW, default_hour=20) == datetime(2026, 9, 14, 9, 0, tzinfo=TZ)
    assert parse_chinese_due_at("6点提醒我背诵", NOW, default_hour=20) == datetime(2026, 9, 14, 6, 0, tzinfo=TZ)


def test_text_carrying_no_time_reference_still_yields_none():
    """没有时间信息时必须返回 None，好让上层如实告知用户，而不是静默套用默认时间。"""
    assert parse_chinese_due_at("提醒我背诵面试经验", NOW, default_hour=20) is None


def test_rule_classifier_reports_exact_time_for_today_evening():
    result = RuleBasedMessageClassifier().classify("今天晚上6点提醒我开始背诵面试经验", NOW)

    assert result.task is not None
    assert result.task.time_kind == "exact"
    assert result.task.due_at == datetime(2026, 9, 13, 18, 0, tzinfo=TZ)
    assert "今天" not in result.task.title
