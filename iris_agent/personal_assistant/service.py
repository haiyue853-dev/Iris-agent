"""Orchestration for all-message archiving and persistent personal tasks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
import logging
from pathlib import Path
import re
from typing import Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iris_agent.gateway.base import InboundMessage
from iris_agent.personal_assistant.classifier import RuleBasedMessageClassifier, parse_chinese_due_at
from iris_agent.personal_assistant.models import ArchiveRecord, IngestOutcome, MessageClassification, PersonalTask, TaskDraft
from iris_agent.personal_assistant.repository import PersonalAssistantRepository


class MessageClassifier(Protocol):
    def classify(self, text: str, now: datetime) -> MessageClassification: ...


class KnowledgeSink(Protocol):
    def enqueue_text(
        self,
        title: str,
        content: str,
        *,
        source_type: str = "manual",
        original_name: str | None = None,
        collection_id: str = "collection-general",
    ) -> object: ...


_TASK_ID = re.compile(r"T-\d+", re.I)
_LOGGER = logging.getLogger(__name__)


class PersonalAssistantService:
    def __init__(
        self,
        root: Path,
        *,
        classifier: MessageClassifier | None = None,
        knowledge_sink: KnowledgeSink | None = None,
        timezone_name: str = "Asia/Shanghai",
        default_reminder_hour: int = 20,
        reminder_interval_days: int = 2,
        quiet_start_hour: int = 22,
        quiet_end_hour: int = 8,
    ) -> None:
        self.repository = PersonalAssistantRepository(Path(root))
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            if timezone_name != "Asia/Shanghai":
                raise
            self.timezone = timezone(timedelta(hours=8), "Asia/Shanghai")
        self.default_reminder_hour = default_reminder_hour
        self.reminder_interval = timedelta(days=reminder_interval_days)
        self.quiet_start_hour = quiet_start_hour
        self.quiet_end_hour = quiet_end_hour
        self.classifier = classifier or RuleBasedMessageClassifier(default_reminder_hour=default_reminder_hour)
        self.knowledge_sink = knowledge_sink

    def ingest(self, message: InboundMessage, *, now: datetime | None = None) -> IngestOutcome:
        moment = self._moment(now)
        raw_id = message.raw.get("message_id") if isinstance(message.raw, dict) else None
        message_id = str(raw_id) if raw_id not in (None, "") else f"local-{uuid4().hex}"
        inserted = self.repository.save_raw(
            platform=message.platform,
            user_id=str(message.user_id),
            message_id=message_id,
            text=message.text,
            created_at=moment,
        )
        if not inserted:
            return IngestOutcome(duplicate=True, reply_override="")

        command = self._handle_command(message.text.strip(), message.platform, str(message.user_id), message_id, moment)
        if command is not None:
            return command

        try:
            classification = self.classifier.classify(message.text, moment)
        except Exception:
            classification = MessageClassification()

        archives: list[ArchiveRecord] = []
        receipt: list[str] = []
        if classification.archive:
            record = self.repository.save_archive(
                classification,
                source_message_id=message_id,
                source_user_id=str(message.user_id),
                original_text=message.text,
                created_at=moment,
            )
            archives.append(record)
            receipt.extend((f"已存档：{record.title}", f"分类：{record.category}"))
            if self.knowledge_sink is not None:
                try:
                    self.knowledge_sink.enqueue_text(
                        record.title,
                        self._knowledge_content(record),
                        source_type="manual",
                        original_name=Path(record.path).name,
                        collection_id="collection-general",
                    )
                    receipt.append("知识库：已加入检索")
                except Exception:
                    _LOGGER.exception("failed to enqueue QQ archive into the knowledge base: %s", record.id)
                    receipt.append("知识库：暂时未能建立索引，文件归档不受影响")

        tasks: list[PersonalTask] = []
        if classification.task is not None:
            draft = classification.task
            if draft.certainty == "confirm":
                self.repository.save_pending(str(message.user_id), draft, message_id, message.text, platform=message.platform)
                question = f"检测到可能的待办：{draft.title}\n需要创建吗？回复“要”确认。"
                if receipt:
                    question = "\n".join(receipt) + "\n\n" + question
                return IngestOutcome(receipt="\n".join(receipt), reply_override=question, archive_records=tuple(archives))
            task = self._create_task(draft, message.platform, str(message.user_id), message_id, message.text, moment)
            tasks.append(task)
            receipt.extend((f"已创建待办【{task.short_id}】{task.title}", f"首次提醒：{self._display_time(task.next_remind_at)}"))
            if notice := self._time_notice(task):
                receipt.append(notice)
            return IngestOutcome(receipt="\n".join(receipt), reply_override="\n".join(receipt), archive_records=tuple(archives), tasks=tuple(tasks))

        archive_receipt = "\n".join(receipt)
        return IngestOutcome(
            receipt=archive_receipt,
            reply_override=archive_receipt if archives else None,
            archive_records=tuple(archives),
        )

    def _handle_command(self, text: str, platform: str, user_id: str, message_id: str, now: datetime) -> IngestOutcome | None:
        if re.fullmatch(r"(?:确认|同意|执行|取消|拒绝)\s*A-\d+", text, re.I):
            # 网关审批命令仍写入原始消息日志，但不需要调用模型分类。
            return IngestOutcome()
        normalized = re.sub(r"\s+", "", text).lower()
        if normalized in {"要", "是", "确认", "创建", "需要", "好的要", "确认创建"}:
            pending = self.repository.pop_pending(user_id)
            if pending is not None:
                draft, source_message_id, source_text, source_platform = pending
                task = self._create_task(replace(draft, certainty="create"), source_platform, user_id, source_message_id, source_text, now)
                reply = f"已创建待办【{task.short_id}】{task.title}\n首次提醒：{self._display_time(task.next_remind_at)}"
                if notice := self._time_notice(task):
                    reply = f"{reply}\n{notice}"
                return IngestOutcome(reply_override=reply, tasks=(task,))
        if normalized in {"不要", "不用", "否", "取消创建"} and self.repository.clear_pending(user_id):
            return IngestOutcome(reply_override="已忽略这条待办候选，原始消息仍保留在存档中。")

        operation = None
        if re.search(r"完成|做完", text):
            operation = "complete"
        elif re.search(r"取消", text) and ("任务" in text or _TASK_ID.search(text) or "这个" in text):
            operation = "cancel"
        elif re.search(r"提醒|再说|顺延", text) and _TASK_ID.search(text):
            operation = "snooze"
        if operation:
            task = self._referenced_task(text, user_id)
            if task is None:
                return IngestOutcome(reply_override="没有找到对应的进行中任务，请回复“查看待办”确认编号。")
            if operation == "complete":
                updated = replace(task, status="completed", updated_at=now)
                self.repository.replace_task(updated)
                return IngestOutcome(reply_override=f"已完成【{task.short_id}】{task.title}", tasks=(updated,))
            if operation == "cancel":
                updated = replace(task, status="cancelled", updated_at=now)
                self.repository.replace_task(updated)
                return IngestOutcome(reply_override=f"已取消【{task.short_id}】{task.title}", tasks=(updated,))
            due_at = parse_chinese_due_at(text, now, self.default_reminder_hour)
            if due_at is None and "下周" in text:
                due_at = self._default_due(now + timedelta(days=7))
            if due_at is None:
                due_at = self._default_due(now + timedelta(days=1))
            updated = replace(task, due_at=due_at, next_remind_at=due_at, updated_at=now)
            self.repository.replace_task(updated)
            return IngestOutcome(reply_override=f"已顺延【{task.short_id}】到 {self._display_time(due_at)}", tasks=(updated,))

        if "待办" in text and re.search(r"查看|看看|哪些|列出|还有|我的", text):
            tasks = self.list_tasks(user_id, active_only=True)
            if not tasks:
                return IngestOutcome(reply_override="目前没有进行中的待办。")
            lines = ["进行中的待办："]
            lines.extend(f"{task.short_id} · {task.title} · 下次提醒 {self._display_time(task.next_remind_at)}" for task in tasks)
            return IngestOutcome(reply_override="\n".join(lines), tasks=tuple(tasks))

        # 这里原先有一个「找一下|查找|搜索|找找」的关键词分支，会把「帮我上网搜索一下1个国内新闻」
        # 当成检索本地存档并直接抢答，agent 根本没机会运行。存档内容已经通过 knowledge_sink 索引进
        # 知识库，改由 agent 的检索路由自己判断该用 search_knowledge / recall 还是 web_search。
        return None

    def _create_task(self, draft: TaskDraft, platform: str, user_id: str, message_id: str, source_text: str, now: datetime) -> PersonalTask:
        due_at = draft.due_at.astimezone(self.timezone) if draft.due_at else self._default_due(now + self.reminder_interval)
        if due_at < now and draft.time_kind != "exact":
            due_at = self._default_due(now + self.reminder_interval)
        return self.repository.create_task(
            draft,
            user_id=user_id,
            platform=platform,
            source_message_id=message_id,
            source_text=source_text,
            created_at=now,
            due_at=due_at,
        )

    @staticmethod
    def _time_notice(task: PersonalTask) -> str:
        """时间没解析出来时必须明说，否则用户会以为「今晚6点」已经记下了。"""
        if task.time_kind != "none":
            return ""
        return "没识别到具体时间，暂按默认时间提醒。要改直接说，例如「改成今晚6点」。"

    def _referenced_task(self, text: str, user_id: str) -> PersonalTask | None:
        match = _TASK_ID.search(text)
        task = self.repository.find_task(match.group(0), user_id) if match else self.repository.latest_active_task(user_id)
        return task if task is not None and task.status == "active" else None

    def list_tasks(self, user_id: str | None = None, *, active_only: bool = False) -> list[PersonalTask]:
        tasks = self.repository.tasks()
        if user_id is not None:
            tasks = [task for task in tasks if task.user_id == str(user_id)]
        if active_only:
            tasks = [task for task in tasks if task.status == "active"]
        return sorted(tasks, key=lambda task: (task.next_remind_at, task.short_id))

    def search_archive(self, query: str, *, user_id: str | None = None, limit: int = 5) -> list[ArchiveRecord]:
        return self.repository.search(query, user_id=user_id, limit=limit)

    def is_quiet(self, now: datetime) -> bool:
        hour = self._moment(now).hour
        if self.quiet_start_hour == self.quiet_end_hour:
            return False
        if self.quiet_start_hour > self.quiet_end_hour:
            return hour >= self.quiet_start_hour or hour < self.quiet_end_hour
        return self.quiet_start_hour <= hour < self.quiet_end_hour

    def due_tasks(self, now: datetime | None = None) -> list[PersonalTask]:
        moment = self._moment(now)
        if self.is_quiet(moment):
            return []
        return [task for task in self.list_tasks(active_only=True) if task.next_remind_at <= moment]

    def mark_notified(self, short_id: str, now: datetime | None = None) -> PersonalTask:
        moment = self._moment(now)
        task = next((item for item in self.repository.tasks() if item.short_id == short_id), None)
        if task is None:
            raise KeyError(short_id)
        updated = replace(
            task,
            reminder_count=task.reminder_count + 1,
            last_reminded_at=moment,
            next_remind_at=moment + self.reminder_interval,
            updated_at=moment,
        )
        return self.repository.replace_task(updated)

    def reminder_text(self, task: PersonalTask) -> str:
        return (
            f"【待办 {task.short_id}】{task.title}\n"
            "这项任务还没有完成。\n\n"
            f"回复：\n完成 {task.short_id}\n明天提醒 {task.short_id}\n取消 {task.short_id}"
        )

    def _moment(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(self.timezone)
        if value.tzinfo is None:
            return value.replace(tzinfo=self.timezone)
        return value.astimezone(self.timezone)

    def _default_due(self, value: datetime) -> datetime:
        local = self._moment(value)
        return datetime.combine(local.date(), time(self.default_reminder_hour), tzinfo=self.timezone)

    @staticmethod
    def _display_time(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _knowledge_content(record: ArchiveRecord) -> str:
        tags = "、".join(record.tags) or "无"
        return (
            f"分类：{record.category}\n"
            f"标签：{tags}\n\n"
            f"摘要：\n{record.summary or '无'}\n\n"
            f"原文：\n{record.original_text.strip()}"
        )
