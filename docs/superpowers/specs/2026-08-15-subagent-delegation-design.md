# 设计规格：P4 子代理委派（一期）

日期：2026-08-15
分支：feature/subagent-delegation（计划）
参考：hermes `agent/subagent_lifecycle.py`、`agent/delegation_context.py`

## 1. 背景与目标

iris 目前已具备记忆（P1）、会话搜索（P2）、动态技能（P3）。主 Agent 每次推理都在**单一消息上下文**里串行进行，当任务包含可独立拆分的子任务（探索代码、分析数据、起草方案）时，主上下文会被无关中间过程污染，且无法并行。

P4 目标：让主 Agent 能通过 **`delegate_task` 工具**，把一个独立子任务委派给**隔离的子代理**执行，子代理用自己的消息上下文、裁剪过的工具集、独立的迭代预算，完成后**只把文本结论返回**给主 Agent。

参照 hermes 的 subagent 机制，但一期做**精简同步版**——hermes 的 `launch/wait/cancel/reconnect` 异步生命周期、跨进程隔离、kanban 调度均不在本期范围。

## 2. 核心概念

**子代理（Subagent）** = 三点隔离：

1. **上下文隔离**：子代理的 messages 只含「子代理 system 提示 + 可选 context 片段 + goal 用户消息」，**不注入主会话历史、不注入记忆**。
2. **工具裁剪**：子代理只拿一个**只读安全工具白名单**的子集，不含写操作（remember/save_skill）、不含 `delegate_task` 本身（防递归）、不含需审批工具、不含 MCP 工具。
3. **独立迭代预算**：子代理用独立的 `AgentLoop` 实例与 `max_rounds`，不占用主会话的轮数。

## 3. 数据模型

新模块 `iris_agent/subagent/`：

```python
# models.py
@dataclass(slots=True)
class SubagentRequest:
    goal: str                       # 子任务目标（必填）
    context: str | None = None      # 可选背景片段
    allowed_tools: list[str] | None = None  # 可选工具白名单（None 用默认）
    max_rounds: int | None = None   # 可选迭代预算（None 用默认）

@dataclass(slots=True)
class SubagentResult:
    ok: bool                        # 是否正常产出文本结论
    result: str                     # 最终文本结论（截断）
    rounds: int                     # 消耗的工具轮数
```

## 4. 执行流程

```
主 Agent 调用 delegate_task(goal, context?, allowed_tools?, max_rounds?)
  → SubagentRunner.run(request)
      → 组装子消息：[system 子代理提示, system 上下文, user goal]
      → 构造裁剪工具集：registry.subset(allowed_tools 或默认白名单)
      → 新建 AgentLoop(provider, 子工具集, max_rounds).run(子消息)
      → 收集最终 message_completed 的 content → SubagentResult
  → 工具返回 {"ok": ..., "result": ..., "rounds": ...}
  → 主 Agent 拿到结论继续推理
```

子代理复用主进程的同一个 `ModelProvider`（同一 client/model/temperature），**同步阻塞**执行（与 iris 现有 `AgentLoop` 同步模型一致）。

## 5. 工具裁剪与安全边界

- 默认白名单（只读）：`current_time`、`list_directory`、`read_file`、`recall`、`use_skill`。
- **明确排除**：`remember`、`save_skill`、`delegate_task`、任何 MCP 工具、任何 `requires_approval=True` 工具。
- **防递归**：子代理工具集不含 `delegate_task`，委派深度固定为 1。
- **截断**：goal 上限 `max_goal_chars`、context 上限 `max_context_chars`、result 上限 `max_result_chars`。
- **不写**：子代理不触碰主会话、记忆账本、技能目录、任务队列。

## 6. 配置

`agent.yaml` 新增 `subagent:` 节 → `SubagentSettings`：

| 键 | 默认 | 说明 |
|----|------|------|
| `max_goal_chars` | 2000 | goal 截断上限 |
| `max_context_chars` | 4000 | context 截断上限 |
| `max_result_chars` | 4000 | 结果截断上限 |
| `default_max_rounds` | 6 | 默认迭代预算 |
| `allowed_tools` | 见白名单 | 默认工具白名单（逗号分隔） |

## 7. 一期不做（留后续）

- 异步委派（launch/wait/cancel/reconnect 分离的生命周期）。
- 并行子代理（同一轮并发多个 delegate）。
- 子代理结果持久化/重连。
- 动态递归深度（子代理再委派）。
- 子代理状态观测（running/耗时/诊断）。

## 8. 验收标准

- [ ] `delegate_task` 工具注册，Agent 可调用。
- [ ] 子代理用隔离上下文执行，主会话不被污染。
- [ ] 子代理工具集裁剪正确（无写工具、无 delegate_task、无审批工具）。
- [ ] 结果截断、goal/context 截断生效。
- [ ] 防递归：子代理无法再委派。
- [ ] 后端全量测试通过，隐私核对无泄漏（子代理不写全局状态）。
