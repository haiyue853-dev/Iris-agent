# 实现计划：P4 子代理委派（一期）

日期：2026-08-15
分支：feature/subagent-delegation

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | 扩展 ToolRegistry 支持子集 + 子代理模型 | `tools/registry.py` 加 `subset()`；`subagent/models.py` |
| 2 | 子代理执行器 | `subagent/runner.py`（复用 AgentLoop） |
| 3 | delegate_task 工具 | `tools/builtin/subagent_tool.py` |
| 4 | 配置 + 装配 | `settings.py` + `bootstrap.py` + `agent.yaml` |
| 5 | 全量验证 | 后端 pytest + 隐私核对 + 文档 |

## 任务细节

### 任务 1：ToolRegistry.subset + 子代理模型
- `ToolRegistry.subset(names: list[str]) -> ToolRegistry`：按名字取工具子集，返回新 registry（未知名字静默跳过）。
- `SubagentRequest` / `SubagentResult` 数据类。
- 测试：`tests/subagent/test_models.py`、`tests/tools/test_registry_subset.py`。

### 任务 2：SubagentRunner
- `SubagentRunner(provider, tool_subset, system_prompt, max_goal_chars, max_context_chars, max_result_chars, default_max_rounds, default_allowed_tools)`。
- `run(request) -> SubagentResult`：组装子消息 → 构造子工具集 → `AgentLoop(...).run(...)` → 收集最终 content。
- 测试：`tests/subagent/test_runner.py`（fake provider 返回预设响应，验证结果传递、轮数、截断、异常终止 ok=False）。

### 任务 3：delegate_task 工具
- `build_delegate_task_tool(runner)`，参数 goal（必填）、context/allowed_tools/max_rounds（可选），`requires_approval=False`。
- 测试：`tests/tools/test_subagent_tool.py`（缺 goal 报错、结果透传、allowed_tools 校验）。

### 任务 4：配置 + 装配
- `SubagentSettings`；`load_settings` 解析 `subagent` 节。
- `bootstrap.py`：构造 `SubagentRunner`，注册 `delegate_task` 工具（工具子集回调 `lambda names: registry.subset(names)`）。
- 测试：`tests/test_bootstrap_services.py` 装配测试。

### 任务 5：全量验证
- 后端 `pytest -q`；隐私核对（子代理不写全局状态、不注入主会话）；提交规格/计划文档。

## 计划自检

- 规格覆盖：任务 1 覆盖工具子集与模型；任务 2 覆盖执行器；任务 3 覆盖工具；任务 4 覆盖配置装配；任务 5 覆盖验证。
- 类型一致性：`SubagentResult` 字段与工具返回 dict 一致；`delegate_task` 复用 `SubagentRunner.run`。
- 安全边界：默认白名单只读；子工具集不含 delegate_task（防递归）；goal/context/result 截断；子代理不写任何全局状态。

## 执行结果（2026-08-15）

- 5 个任务全部完成并提交（5 个 commit）：工具子集+模型 → 执行器 → delegate_task 工具 → 配置装配 → 文档。
- 全量验证：后端 `391 passed, 3 skipped, 0 failed`（新增 21 条子代理测试全绿）。
- 防递归与隐私核对通过：子代理默认工具集不含 delegate_task/remember/save_skill；子代理不写主会话、记忆、技能、任务队列。

