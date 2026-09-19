"""Shared guard: keep assistant-behaviour rules out of the long-term memory ledger.

Lives in ``iris_agent.memory`` (rather than next to the ``remember`` tool) so that both the
tool and automatic capture can use it **without importing ``iris_agent.tools.builtin``** —
importing that package runs its ``__init__``, which pulls in the subagent tools, which import
``iris_agent.core.agent``, closing a cycle.
"""

from __future__ import annotations

import re

_DIRECT_BEHAVIOR_RULE = re.compile(
    r"(?:系统|开发者)?提示词|system\s*prompt|developer\s*(?:message|instruction)|"
    r"(?:agent|助手|模型).{0,12}(?:工作方式|行为|角色|规则|流程|提示词)",
    re.IGNORECASE,
)
_DIRECTIVE_MARKERS = (
    "以后", "每次", "始终", "永远", "必须", "务必", "不要", "不得", "禁止", "直接", "跳过", "忽略",
    "always", "never", "must", "should", "do not", "don't", "skip", "ignore",
)
_BEHAVIOR_MARKERS = (
    "回复", "回答", "输出", "代码生成", "审核", "评审", "工具", "角色", "工作方式", "工作流程",
    "response", "reply", "output", "tool", "role", "workflow", "agent", "assistant", "prompt",
)


def is_agent_behavior_rule(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    if _DIRECT_BEHAVIOR_RULE.search(normalized):
        return True
    return any(marker in normalized for marker in _DIRECTIVE_MARKERS) and any(
        marker in normalized for marker in _BEHAVIOR_MARKERS
    )
