from __future__ import annotations

import json

from iris_agent.core.models import Message
from iris_agent.reports.models import ReportSections, ReportSourceMessage

GENERATION_SYSTEM_PROMPT = """你是 Iris Agent 的工作日报整理助手。
请严格依据输入事实，生成适合向领导或团队汇报的简洁中文日报。
不要虚构完成项、数字、进度或问题；没有内容的章节使用空数组。
只返回一个 JSON 对象，不要返回 Markdown、代码块或解释。
对象必须且只能包含 completed、in_progress、problems、next_day、assistance 五个键，
每个值必须是字符串数组。成果优先，问题描述客观，明日计划应可执行。"""

REVISION_SYSTEM_PROMPT = """你是 Iris Agent 的工作日报修改助手。
请按照用户要求修改现有日报，不得添加输入中不存在的事实。
只返回一个 JSON 对象，不要返回 Markdown、代码块或解释。
对象必须且只能包含 completed、in_progress、problems、next_day、assistance 五个键，
每个值必须是字符串数组。"""


def build_generate_messages(
    notes: str,
    chat: tuple[ReportSourceMessage, ...],
) -> list[Message]:
    source = {
        "manual_notes": notes,
        "chat": [{"role": item.role, "content": item.content} for item in chat],
    }
    return [
        Message(role="system", content=GENERATION_SYSTEM_PROMPT),
        Message(role="user", content=json.dumps(source, ensure_ascii=False)),
    ]


def build_revision_messages(sections: ReportSections, instruction: str) -> list[Message]:
    payload = {
        "current_report": sections.to_dict(),
        "instruction": instruction,
    }
    return [
        Message(role="system", content=REVISION_SYSTEM_PROMPT),
        Message(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]
