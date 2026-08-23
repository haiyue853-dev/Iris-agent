# 聊天与工具协作式取消实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 停止按钮同时取消前端生成状态和后端 AI 工作流，并让未完成工具立即显示为已停止。

**架构：** 后端增加线程安全的活动聊天取消注册表，由聊天流注册任务并把取消检查函数传入 AgentService/AgentLoop；任务取消接口优先取消活动聊天，否则沿用队列取消。前端 adapter 保存 `task_id`，监听 assistant-ui abort 后调用任务取消接口，以 cancelled 状态收敛所有未完成工具，并使用独立 transport controller 安全处理 task_id 尚未到达的竞态。

**技术栈：** Python 3.13、FastAPI、threading.Event、React 19、TypeScript、assistant-ui、Vitest、pytest

---

## 文件结构

- 创建 `iris_agent/core/cancellation.py`：活动聊天任务与线程安全取消信号注册表。
- 修改 `iris_agent/core/agent.py`：在模型与工具边界检查取消信号，丢弃迟到结果。
- 修改 `iris_agent/api/app.py`：聊天流注册/注销取消信号并传入 AgentService。
- 修改 `iris_agent/api/tasks_api.py`：任务取消接口支持活动聊天，终态取消保持幂等。
- 修改 `tests/core/test_agent_loop.py`、`tests/api/test_tasks_api.py`：后端取消回归测试。
- 修改 `web-react/src/lib/irisRuntime.ts`：保存 task_id、发起后端取消、以 cancelled 状态结束。
- 修改 `web-react/src/api/chat.ts`：允许 adapter 使用独立 transport signal。
- 修改 `web-react/src/components/assistant-ui/tool-group.tsx` 与 `tool-fallback.tsx`：未完成工具显示“已停止”。
- 修改 `web-react/tests/IrisRuntimeThinking.test.ts`、`ThreadRichParts.theme.test.ts`：前端取消与显示测试。

### 任务 1：后端 Agent 取消边界

**文件：**
- 创建：`iris_agent/core/cancellation.py`
- 修改：`iris_agent/core/agent.py`
- 测试：`tests/core/test_agent_loop.py`

- [ ] **步骤 1：编写失败测试**

```py
def test_cancellation_after_tool_return_discards_result_and_stops_next_round():
    cancelled = False
    provider = TwoRoundProvider()
    tools = registry_with_tool(lambda: cancel_and_return())
    events = list(AgentLoop(provider, tools).run(messages, is_cancelled=lambda: cancelled))
    assert not any(event.type == "tool_finished" for event in events)
    assert provider.calls == 1
```

同时覆盖：模型请求前已取消不调用 provider；第一个工具完成后取消不会启动第二个工具。

- [ ] **步骤 2：运行红灯**

运行：`.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_loop.py -q`

预期：FAIL，因为 `AgentLoop.run` 尚不接受 `is_cancelled`。

- [ ] **步骤 3：实现取消注册表**

```py
class ChatCancellationRegistry:
    def register(self, task_id: str) -> Event: ...
    def cancel(self, task_id: str) -> bool: ...
    def unregister(self, task_id: str) -> None: ...
```

内部以 `RLock` 保护 `dict[str, Event]`；`cancel()` 找到活动任务后设置 Event 并返回 `True`。

- [ ] **步骤 4：实现 Agent 边界检查**

为 `AgentLoop.run`、`AgentService.run` 和审批恢复路径增加可选 `is_cancelled: Callable[[], bool]`。在 provider 调用前、每个工具开始前、`registry.invoke()` 返回后、进入下一轮前检查；取消后直接结束生成器，不发送迟到的 `tool_finished` 或 `message_completed`。

- [ ] **步骤 5：运行绿灯**

运行：`.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_loop.py -q`

预期：全部 PASS。

### 任务 2：聊天任务取消 API

**文件：**
- 修改：`iris_agent/api/app.py`
- 修改：`iris_agent/api/tasks_api.py`
- 测试：`tests/api/test_tasks_api.py`

- [ ] **步骤 1：编写失败 API 测试**

```py
def test_cancelling_active_chat_sets_execution_signal(client, blocking_tool):
    # 启动聊天流并等待 tool_started，再 DELETE task id
    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "stopped"
    blocking_tool.release()
    assert provider.calls == 1
```

增加终态幂等测试：对 stopped/completed 任务再次 DELETE 返回当前任务而不是 409。

- [ ] **步骤 2：运行红灯**

运行：`.\.venv\Scripts\python.exe -m pytest tests/api/test_tasks_api.py -q`

预期：活动聊天取消因只支持 task queue 而失败。

- [ ] **步骤 3：连接聊天流与注册表**

在 `create_app` 创建 `ChatCancellationRegistry`，聊天流取得 `task_id` 后注册 Event，并调用：

```py
for event in service.run(..., is_cancelled=cancel_event.is_set):
    ...
```

在 `finally` 中注销；`GeneratorExit` 仍停止任务并清理审批记录。

- [ ] **步骤 4：扩展取消路由**

`register_task_routes` 接收 `cancel_active_chat: Callable[[str], bool] | None`。DELETE 时先返回现有终态；若活动聊天取消成功，调用 `task_center.stop(task_id)`；否则调用现有 `task_queue.cancel()`。

- [ ] **步骤 5：运行后端测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/api/test_tasks_api.py tests/api/test_app.py tests/core/test_agent_loop.py -q`

预期：全部 PASS。

### 任务 3：前端取消任务并收敛消息状态

**文件：**
- 修改：`web-react/src/lib/irisRuntime.ts`
- 修改：`web-react/src/api/chat.ts`
- 测试：`web-react/tests/IrisRuntimeThinking.test.ts`

- [ ] **步骤 1：编写失败 adapter 测试**

```ts
it("cancels the backend task and returns cancelled when aborted", async () => {
  // stream 发出 task_started 后保持打开
  abortController.abort();
  expect(cancelTask).toHaveBeenCalledWith("task-1");
  expect(final.status).toEqual({ type: "incomplete", reason: "cancelled" });
});
```

增加竞态测试：abort 先发生、`task_started` 后到达，只补发一次 `cancelTask`。

- [ ] **步骤 2：运行红灯**

运行：`npm test -- --run tests/IrisRuntimeThinking.test.ts`

预期：FAIL，因为 adapter 当前 abort 时直接返回且不调用取消接口。

- [ ] **步骤 3：实现 transport 与任务取消状态机**

- 运行实例维护 `taskId`、`cancelRequested`、`cancelPromise` 和独立 `AbortController`。
- `applyEvent(task_started)` 保存 id；若已请求取消，立即且仅一次调用 `cancelTask(taskId)`。
- assistant abort listener 设置 `cancelRequested`；已有 id 时调用取消；待请求完成后中止 transport。
- generator 最终 yield `{ type: "incomplete", reason: "cancelled" }`，而不是静默 return。
- `finally` 移除 abort listener，确保错误不会覆盖 cancelled 状态。

- [ ] **步骤 4：运行前端 adapter 测试**

运行：`npm test -- --run tests/IrisRuntimeThinking.test.ts`

预期：全部 PASS。

### 任务 4：工具取消显示

**文件：**
- 修改：`web-react/src/lib/irisRuntime.ts`
- 修改：`web-react/src/components/assistant-ui/tool-group.tsx`
- 修改：`web-react/src/components/assistant-ui/tool-fallback.tsx`
- 测试：`web-react/tests/ThreadRichParts.theme.test.ts`

- [ ] **步骤 1：编写失败显示测试**

断言 cancelled 消息中 `result === undefined` 的工具被映射为 `state: "cancelled"`，已完成工具仍为 `completed`；分组摘要和单项 fallback 显示“已停止”且没有 `animate-spin`。

- [ ] **步骤 2：运行红灯**

运行：`npm test -- --run tests/ThreadRichParts.theme.test.ts tests/IrisRuntimeThinking.test.ts`

预期：FAIL，因为工具组状态目前只允许 running/completed/failed。

- [ ] **步骤 3：实现取消状态**

扩展 `IrisToolGroupItem.state` 为 `"running" | "completed" | "failed" | "cancelled"`。adapter 取消时仅把未完成工具映射为 cancelled；渲染层使用中性图标和“已停止”文字，取消状态不使用 spinner。

- [ ] **步骤 4：运行绿灯**

运行：`npm test -- --run tests/ThreadRichParts.theme.test.ts tests/IrisRuntimeThinking.test.ts`

预期：全部 PASS。

### 任务 5：完整验证

- [ ] **步骤 1：运行完整后端测试**

运行：`.\.venv\Scripts\python.exe -m pytest -q`

预期：0 failed。

- [ ] **步骤 2：运行完整前端测试**

运行：`npm test -- --run`

预期：0 failed。

- [ ] **步骤 3：运行构建与 lint**

运行：`npm run build` 和 `npm run lint`

预期：构建退出码 0；lint 0 errors，允许现有 Fast Refresh 警告。

- [ ] **步骤 4：核对边界**

确认停止后工具不再转圈、后续模型/工具不启动、迟到结果被丢弃、终态取消幂等，并且没有引入线程强杀或工具子进程迁移。

> 说明：当前目录不是 Git 仓库，因此省略 commit 和 worktree 步骤。
