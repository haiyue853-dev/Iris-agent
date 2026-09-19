"""Deterministic and provider-assisted classification of incoming QQ text."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from typing import Callable

from iris_agent.core.models import Message
from iris_agent.personal_assistant.models import MessageClassification, TaskDraft
from iris_agent.providers.base import ModelProvider


_DIRECT_TASK = re.compile(r"提醒我|记得(?:提醒我)?|待办|我要(?:在|于|明天|后天|下周|周|过几天)|别忘了")
_TIME_WORD = re.compile(r"明天|明晚|后天|\d+\s*天后|过几天|有空|改天|下周|周[一二三四五六日天]|\d{1,2}月\d{1,2}[日号]")
_TODAY_WORD = re.compile(r"今天|今晚|今日")


def _clock_match(text: str) -> tuple[int, int] | None:
    """解析文本中显式写出的钟点；没有写时间时返回 None。

    区分「没写时间」和「写的时间恰好等于默认值」很重要：只有前者才该回退到默认时间。
    """
    match = re.search(r"(上午|早上|中午|下午|晚上|今晚)\s*(\d{1,2})(?:[:：点时](\d{1,2})?分?)?", text)
    if match:
        period, raw_hour, raw_minute = match.groups()
    else:
        match = re.search(r"(?<![\d-])(\d{1,2})([:：点时])(\d{1,2})?分?", text)
        if not match:
            return None
        period = None
        raw_hour, _, raw_minute = match.groups()
    hour = min(int(raw_hour), 23)
    minute = min(int(raw_minute or 0), 59)
    if period in {"下午", "晚上", "今晚"} and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12
    if period in {"上午", "早上"} and hour == 12:
        hour = 0
    return hour, minute


def _clock(text: str, default_hour: int) -> tuple[int, int]:
    return _clock_match(text) or (default_hour, 0)


def parse_chinese_due_at(text: str, now: datetime, default_hour: int = 20) -> datetime | None:
    clock = _clock_match(re.sub(r"T-\d+", "", text, flags=re.I))
    hour, minute = clock if clock else (default_hour, 0)
    target_date = None
    if "现在" in text or "马上" in text:
        return now
    if "后天" in text:
        target_date = (now + timedelta(days=2)).date()
    elif "明天" in text or "明晚" in text:
        target_date = (now + timedelta(days=1)).date()
    elif match := re.search(r"(\d+)\s*天后", text):
        target_date = (now + timedelta(days=max(1, int(match.group(1))))).date()
    elif match := re.search(r"(\d{1,2})月(\d{1,2})[日号]", text):
        month, day = int(match.group(1)), int(match.group(2))
        year = now.year
        try:
            target_date = now.date().replace(year=year, month=month, day=day)
            if target_date < now.date():
                target_date = target_date.replace(year=year + 1)
        except ValueError:
            return None
    elif match := re.search(r"(?:下周|周)([一二三四五六日天])", text):
        weekday = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}[match.group(1)]
        days = (weekday - now.weekday()) % 7
        if "下周" in match.group(0):
            days = days + 7 if days else 7
        elif days == 0:
            days = 7
        target_date = (now + timedelta(days=days)).date()
    elif "下周" in text:
        days_to_monday = 7 - now.weekday()
        target_date = (now + timedelta(days=days_to_monday)).date()
    elif _TODAY_WORD.search(text) or clock is not None:
        # 「今天/今晚」以及「只给了钟点、没给日期」的说法都按今天算；若今天该时刻已经过了就顺延到明天，
        # 而不是让调用方把它当成过期时间丢掉。
        target_date = now.date()
        moment = datetime.combine(target_date, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)
        if moment <= now:
            target_date = (now + timedelta(days=1)).date()
    if target_date is None:
        return None
    return datetime.combine(target_date, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)


def _title(text: str) -> str:
    cleaned = re.sub(r"^(?:请|帮我|麻烦你)?\s*(?:提醒我|记得|待办[:：]?|别忘了)\s*", "", text.strip())
    cleaned = re.sub(r"(?:今天|今晚|今日|明天|明晚|后天|\d+\s*天后|过几天|有空|改天|下周[一二三四五六日天]?|周[一二三四五六日天])", "", cleaned)
    cleaned = re.sub(r"(?:(?:上午|早上|中午|下午|晚上|今晚)\s*)?\d{1,2}(?:[:：点时]\d{0,2}分?)?", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ，。,.：:")[:80] or text.strip()[:80]


class RuleBasedMessageClassifier:
    def __init__(self, *, default_reminder_hour: int = 20):
        self.default_reminder_hour = default_reminder_hour

    def classify(self, text: str, now: datetime) -> MessageClassification:
        normalized = text.strip()
        direct = bool(_DIRECT_TASK.search(normalized))
        has_time = bool(_TIME_WORD.search(normalized))
        due_at = parse_chinese_due_at(normalized, now, self.default_reminder_hour)
        time_kind = "exact" if due_at else ("vague" if re.search(r"过几天|有空|改天", normalized) else "none")
        task = None
        if direct:
            task = TaskDraft(_title(normalized), certainty="create", time_kind=time_kind, due_at=due_at)
        elif has_time and len(normalized) >= 8:
            task = TaskDraft(_title(normalized), certainty="confirm", time_kind=time_kind, due_at=due_at)

        archive = len(normalized) >= 40 or "http://" in normalized or "https://" in normalized or "\n" in normalized
        compact = re.sub(r"\s+", " ", normalized)
        first_line = next((line.strip() for line in normalized.splitlines() if line.strip()), compact)
        category = "其他"
        category_keywords = {
            "工作": ("项目", "工作", "会议", "客户", "服务器", "代码", "部署", "需求"),
            "学习": ("学习", "教程", "课程", "论文", "知识", "面试"),
            "生活": ("生活", "缴费", "快递", "医院", "购物", "旅行"),
            "灵感": ("灵感", "想法", "创意", "点子"),
        }
        for candidate, keywords in category_keywords.items():
            if any(keyword.lower() in normalized.lower() for keyword in keywords):
                category = candidate
                break
        tags = tuple(keyword for keyword in ("Iris", "QQ", "NapCat", "Agent", "Python", "服务器", "面试") if keyword.lower() in normalized.lower())
        return MessageClassification(
            archive=archive,
            title=first_line[:60],
            summary=compact[:200],
            category=category,
            tags=tags,
            task=task,
        )


class ProviderMessageClassifier:
    """Use the configured chat model for rich organisation, with deterministic fallback."""

    def __init__(self, provider: Callable[[], ModelProvider], fallback: RuleBasedMessageClassifier | None = None):
        self.provider = provider
        self.fallback = fallback or RuleBasedMessageClassifier()

    def classify(self, text: str, now: datetime) -> MessageClassification:
        baseline = self.fallback.classify(text, now)
        if len(text.strip()) < 20 and not baseline.archive and baseline.task is not None:
            return baseline
        if len(text.strip()) < 12 and baseline.task is None:
            return baseline
        prompt = (
            "你是私人资料与待办分类器。只返回一个 JSON 对象，不要 Markdown。"
            "字段：archive(boolean)、title、summary、category(工作/学习/生活/灵感/其他)、tags(string[])、"
            "task(null 或 {title,certainty:create|confirm,time_kind:exact|vague|none,due_at:带时区ISO时间或null})。"
            "明确对助手说提醒我/待办/记得时 certainty=create；复制来的通知即使有日期也只能 confirm。"
            "长资料、链接、通知和有复用价值的信息 archive=true；寒暄和普通控制指令为 false。"
            f"当前时间：{now.isoformat()}"
        )
        try:
            response = self.provider().complete([Message(role="system", content=prompt), Message(role="user", content=text)], [])
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
            value = json.loads(raw)
            task_value = value.get("task")
            task = TaskDraft.from_dict(task_value) if isinstance(task_value, dict) else None
            category = str(value.get("category", "其他"))
            return MessageClassification(
                archive=bool(value.get("archive", False)),
                title=str(value.get("title", "")).strip()[:100],
                summary=str(value.get("summary", "")).strip()[:1000],
                category=category if category in {"工作", "学习", "生活", "灵感", "其他"} else "其他",
                tags=tuple(str(item).strip()[:30] for item in value.get("tags", []) if str(item).strip())[:12],
                task=task,
            )
        except Exception:
            return baseline
