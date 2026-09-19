from datetime import datetime, timedelta, timezone

import pytest

from iris_agent.gateway.base import InboundMessage
from iris_agent.personal_assistant.models import MessageClassification, TaskDraft
from iris_agent.personal_assistant.scheduler import PersonalReminderScheduler
from iris_agent.personal_assistant.service import PersonalAssistantService


SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
NOW = datetime(2026, 9, 13, 10, 0, tzinfo=SHANGHAI)


class QueueClassifier:
    def __init__(self, *items: MessageClassification):
        self.items = list(items)

    def classify(self, text: str, now: datetime) -> MessageClassification:
        if not self.items:
            return MessageClassification()
        return self.items.pop(0)


class RecordingKnowledgeSink:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    def enqueue_text(self, title, content, **kwargs):
        self.calls.append((title, content, kwargs))
        if self.error is not None:
            raise self.error
        return object()


def message(text: str, message_id: int, user_id: str = "42", platform: str = "qq") -> InboundMessage:
    return InboundMessage(platform, user_id, text, raw={"message_id": message_id})


def test_every_message_is_written_once_to_daily_raw_journal(tmp_path):
    service = PersonalAssistantService(tmp_path, classifier=QueueClassifier())

    first = service.ingest(message("普通聊天也需要保存", 100), now=NOW)
    duplicate = service.ingest(message("普通聊天也需要保存", 100), now=NOW)

    journal = tmp_path / "raw" / "2026" / "09" / "2026-09-13.md"
    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert journal.read_text(encoding="utf-8").count("普通聊天也需要保存") == 1


def test_useful_message_is_organized_as_searchable_markdown(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(
            archive=True,
            title="Iris QQ 接入注意事项",
            summary="需要观察 NapCat 的连接稳定性。",
            category="工作",
            tags=("Iris", "QQ", "NapCat"),
        )
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)

    outcome = service.ingest(message("这是一段需要长期保存的 NapCat 配置资料", 101), now=NOW)

    saved = list((tmp_path / "archive" / "工作").glob("*.md"))
    assert len(saved) == 1
    content = saved[0].read_text(encoding="utf-8")
    assert "# Iris QQ 接入注意事项" in content
    assert "需要观察 NapCat 的连接稳定性" in content
    assert "这是一段需要长期保存的 NapCat 配置资料" in content
    assert "已存档：Iris QQ 接入注意事项" in outcome.receipt
    assert outcome.reply_override == outcome.receipt
    assert service.search_archive("NapCat")[0].title == "Iris QQ 接入注意事项"


def test_archived_message_is_added_to_retrievable_knowledge(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(
            archive=True,
            title="远程办公资料",
            summary="一段可供以后检索的资料。",
            category="工作",
            tags=("远程", "资料"),
        )
    )
    knowledge = RecordingKnowledgeSink()
    service = PersonalAssistantService(tmp_path, classifier=classifier, knowledge_sink=knowledge)

    service.ingest(message("远程办公的原始资料内容", 113), now=NOW)

    assert len(knowledge.calls) == 1
    title, content, options = knowledge.calls[0]
    assert title == "远程办公资料"
    assert "一段可供以后检索的资料" in content
    assert "远程办公的原始资料内容" in content
    assert options["source_type"] == "manual"
    assert options["collection_id"] == "collection-general"
    assert options["original_name"].endswith(".md")


def test_knowledge_index_failure_does_not_lose_archive(tmp_path):
    classifier = QueueClassifier(MessageClassification(archive=True, title="仍要保存", category="其他"))
    knowledge = RecordingKnowledgeSink(RuntimeError("index unavailable"))
    service = PersonalAssistantService(tmp_path, classifier=classifier, knowledge_sink=knowledge)

    outcome = service.ingest(message("知识库暂时失败时也必须归档", 114), now=NOW)

    assert "已存档：仍要保存" in outcome.receipt
    assert len(list((tmp_path / "archive" / "其他").glob("*.md"))) == 1


def test_no_time_task_gets_first_reminder_two_days_later(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("整理项目资料", certainty="create", time_kind="none"))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)

    outcome = service.ingest(message("提醒我整理项目资料", 102), now=NOW)

    task = service.list_tasks("42")[0]
    assert task.short_id == "T-001"
    assert task.next_remind_at == datetime(2026, 9, 15, 20, 0, tzinfo=SHANGHAI)
    assert "已创建待办【T-001】整理项目资料" in outcome.receipt


def test_task_remembers_the_channel_that_created_it(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("企业微信待办", certainty="create", time_kind="none"))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)

    service.ingest(message("提醒我处理企业微信待办", 120, platform="wecom"), now=NOW)

    assert service.list_tasks("42")[0].platform == "wecom"


def test_uncertain_task_requires_confirmation_before_creation(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("明天提交材料", certainty="confirm", time_kind="exact", due_at=datetime(2026, 9, 14, 20, 0, tzinfo=SHANGHAI)))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)

    possible = service.ingest(message("通知：请于明天提交材料", 103), now=NOW)
    confirmed = service.ingest(message("要", 104), now=NOW + timedelta(minutes=1))

    assert service.list_tasks("42")[0].title == "明天提交材料"
    assert "需要创建吗" in possible.reply_override
    assert "已创建待办【T-001】" in confirmed.reply_override


def test_reminders_repeat_until_task_is_completed(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("续费服务器", certainty="create", time_kind="exact", due_at=NOW))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)
    service.ingest(message("现在提醒我续费服务器", 105), now=NOW)

    due = service.due_tasks(NOW)
    assert [task.short_id for task in due] == ["T-001"]
    service.mark_notified("T-001", NOW)
    assert service.list_tasks("42")[0].next_remind_at == NOW + timedelta(days=2)

    completed = service.ingest(message("完成 T-001", 106), now=NOW + timedelta(minutes=1))

    assert "已完成【T-001】" in completed.reply_override
    assert service.list_tasks("42", active_only=True) == []
    assert service.due_tasks(NOW + timedelta(days=3)) == []


def test_snooze_and_cancel_commands_update_task_without_model(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("整理资料", certainty="create", time_kind="none"))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)
    service.ingest(message("提醒我整理资料", 107), now=NOW)

    snoozed = service.ingest(message("明天提醒 T-001", 108), now=NOW)
    assert "已顺延【T-001】" in snoozed.reply_override
    assert service.list_tasks("42")[0].next_remind_at == datetime(2026, 9, 14, 20, 0, tzinfo=SHANGHAI)

    cancelled = service.ingest(message("取消 T-001", 109), now=NOW)
    assert "已取消【T-001】" in cancelled.reply_override
    assert service.list_tasks("42")[0].status == "cancelled"


def test_scheduler_respects_quiet_hours_and_marks_only_successful_pushes(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("夜间任务", certainty="create", time_kind="exact", due_at=datetime(2026, 9, 13, 23, 0, tzinfo=SHANGHAI)))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)
    service.ingest(message("今晚提醒我夜间任务", 110), now=NOW)
    pushes: list[tuple[str, str, str]] = []
    results = iter((False, True))

    def push(platform: str, user_id: str, text: str) -> bool:
        pushes.append((platform, user_id, text))
        return next(results)

    scheduler = PersonalReminderScheduler(service, push)

    assert scheduler.run_pending(datetime(2026, 9, 13, 23, 0, tzinfo=SHANGHAI)) == 0
    assert pushes == []
    morning = datetime(2026, 9, 14, 8, 0, tzinfo=SHANGHAI)
    assert scheduler.run_pending(morning) == 0
    assert service.list_tasks("42")[0].reminder_count == 0
    assert scheduler.run_pending(morning + timedelta(minutes=5)) == 1
    assert service.list_tasks("42")[0].reminder_count == 1
    assert pushes[-1][0] == "qq"
    assert "【待办 T-001】夜间任务" in pushes[-1][2]


def test_real_rule_classifier_handles_vague_reminder_and_survives_restart(tmp_path):
    first = PersonalAssistantService(tmp_path)

    outcome = first.ingest(message("过几天提醒我整理报销材料", 111), now=NOW)

    assert "已创建待办【T-001】" in outcome.reply_override
    second = PersonalAssistantService(tmp_path)
    restored = second.list_tasks("42", active_only=True)
    assert len(restored) == 1
    assert restored[0].time_kind == "vague"
    assert restored[0].next_remind_at == datetime(2026, 9, 15, 20, 0, tzinfo=SHANGHAI)


def test_raw_message_is_saved_before_agent_processing_can_fail(tmp_path):
    personal = PersonalAssistantService(tmp_path, classifier=QueueClassifier())

    personal.ingest(message("即使后续 Agent 失败也不能丢", 112), now=NOW)

    journal = tmp_path / "raw" / "2026" / "09" / "2026-09-13.md"
    assert "即使后续 Agent 失败也不能丢" in journal.read_text(encoding="utf-8")


def test_qq_approval_command_is_saved_without_calling_classifier(tmp_path):
    class SpyClassifier:
        calls = 0

        def classify(self, text, now):
            self.calls += 1
            return MessageClassification(archive=True, title="不应存档")

    classifier = SpyClassifier()
    personal = PersonalAssistantService(tmp_path, classifier=classifier)

    outcome = personal.ingest(message("确认 A-001", 115), now=NOW)

    assert classifier.calls == 0
    assert outcome.reply_override is None
    journal = tmp_path / "raw" / "2026" / "09" / "2026-09-13.md"
    assert "确认 A-001" in journal.read_text(encoding="utf-8")


def test_end_to_end_today_evening_becomes_exact_not_the_default_interval(tmp_path):
    """回归 T-001：真实规则分类器下，说「今天晚上6点」曾被记成两天后的默认时间。"""
    service = PersonalAssistantService(tmp_path)

    outcome = service.ingest(message("今天晚上6点提醒我开始背诵面试经验", 117), now=NOW)

    task = service.list_tasks("42")[0]
    assert task.time_kind == "exact"
    assert task.next_remind_at == datetime(2026, 9, 13, 18, 0, tzinfo=SHANGHAI)
    assert "没识别到具体时间" not in outcome.reply_override


def test_task_without_a_recognised_time_says_so_instead_of_guessing_silently(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("整理项目资料", certainty="create", time_kind="none"))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)

    outcome = service.ingest(message("提醒我整理项目资料", 115), now=NOW)

    assert "没识别到具体时间" in outcome.reply_override


def test_task_with_an_exact_time_gets_no_guess_notice(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("续费服务器", certainty="create", time_kind="exact", due_at=NOW))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)

    outcome = service.ingest(message("现在提醒我续费服务器", 116), now=NOW)

    assert "没识别到具体时间" not in outcome.reply_override


def test_confirmed_task_without_a_recognised_time_also_gets_the_notice(tmp_path):
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("整理资料", certainty="confirm", time_kind="none"))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)
    service.ingest(message("通知：请整理资料", 118), now=NOW)

    confirmed = service.ingest(message("要", 119), now=NOW + timedelta(minutes=1))

    assert "没识别到具体时间" in confirmed.reply_override


@pytest.mark.parametrize(
    "text",
    [
        "帮我上网搜索一下1个国内新闻",
        "帮我搜索一下下周的天气",
        "帮我上网查一下今天的汇率",
        "找一下我之前保存的资料",
        "搜索存档里的RAG资料",
    ],
)
def test_content_requests_are_left_to_the_agent_instead_of_being_keyword_hijacked(tmp_path, text):
    """回归：这些说法曾被个人助手的「找一下|查找|搜索|找找」分支当成检索本地存档并直接抢答，
    导致 agent 从不运行、web_search / search_knowledge 都没机会执行。"""
    service = PersonalAssistantService(tmp_path, classifier=QueueClassifier())

    outcome = service.ingest(message(text, 130), now=NOW)

    assert outcome.reply_override is None


def test_task_control_commands_still_answer_deterministically(tmp_path):
    """去掉关键词抢答后，真正的控制指令仍应就地处理，不依赖模型。"""
    classifier = QueueClassifier(
        MessageClassification(task=TaskDraft("整理资料", certainty="create", time_kind="none"))
    )
    service = PersonalAssistantService(tmp_path, classifier=classifier)
    service.ingest(message("提醒我整理资料", 131), now=NOW)

    listed = service.ingest(message("查看待办", 132), now=NOW)
    completed = service.ingest(message("完成 T-001", 133), now=NOW)

    assert "进行中的待办" in listed.reply_override
    assert "已完成【T-001】" in completed.reply_override
