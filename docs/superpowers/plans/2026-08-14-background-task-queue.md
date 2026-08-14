# 后台任务队列一期实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 React 主聊天切换为可持久化、单工作者执行、完成后回填会话的后台任务队列。

**架构：** `TaskQueueService` 把完整用户消息保存在独立 JSON 队列账本，并协调一个后台线程。`TaskCenterService` 仍是任务状态与安全时间线的唯一公共来源。FastAPI 管理工作者生命周期；前端通过 REST 提交、审批、取消和轮询任务，不保持聊天 NDJSON 连接。

**技术栈：** Python 3、FastAPI、线程与条件变量、原子 JSON 仓储、Pytest、React、TypeScript、Vitest。

---

## 文件结构

- 创建：`iris_agent/task_queue/models.py`、`repository.py`、`service.py`、`__init__.py`——私有作业、原子账本与单工作者。
- 创建：`tests/task_queue/test_repository.py`、`tests/task_queue/test_service.py`——账本、FIFO、审批、取消和恢复。
- 修改：`iris_agent/task_center/models.py`、`service.py`——`queued` 状态与安全生命周期事件。
- 修改：`iris_agent/config/settings.py`、`agent.yaml`、`iris_agent/bootstrap.py`、`server.py`——队列设置、构建与生命周期。
- 修改：`iris_agent/api/schemas.py`、`tasks_api.py`、`app.py`；创建 `tests/api/test_task_queue_api.py`——队列 REST API。
- 修改：`web-react/src/types.ts`、`api/tasks.ts`、`hooks/useChat.ts`、`components/ChatContainer.tsx`、`components/tasks/TaskCenterPage.tsx`、`App.tsx`、`App.css` 及对应 Vitest 文件——提交、轮询、审批、取消与展示。

### 任务 1：先扩展任务中心状态

**文件：** 修改 `iris_agent/task_center/models.py`、`iris_agent/task_center/service.py`；测试 `tests/task_center/test_service.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_queued_task_starts_then_stops(tmp_path):
    service = TaskCenterService(tmp_path)
    task = service.create_queued_task("session-1", "整理项目状态")
    assert task.status == "queued"
    assert service.start(task.id).status == "running"
    assert service.request_stop(task.id).status == "running"
    assert service.stop(task.id).status == "stopped"
```

- [ ] **步骤 2：验证测试为红色**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/task_center/test_service.py::test_queued_task_starts_then_stops -q`  
预期：FAIL，缺少 `create_queued_task`。

- [ ] **步骤 3：实现最小状态转换**

```python
def _create(self, session_id: str, user_message: str, status: str, event_type: str, label: str) -> AgentTask:
    timestamp = _now()
    task = AgentTask(id=f"task_{uuid4().hex}", session_id=session_id, request_summary=user_message.strip()[:120], status=status, created_at=timestamp, updated_at=timestamp, events=(self._event(event_type, label, timestamp=timestamp),))
    with self.repository.transaction():
        tasks = self.repository.load()
        self._save_bounded([*tasks, task])
    return task

def create_queued_task(self, session_id: str, user_message: str) -> AgentTask:
    return self._create(session_id, user_message, "queued", "request_queued", "已加入队列")

def start(self, task_id: str) -> AgentTask:
    return self._append(task_id, "execution_started", "开始执行", status="running")

def request_stop(self, task_id: str) -> AgentTask:
    return self._append(task_id, "stop_requested", "已请求停止")
```

让 `_validate_transition` 只允许 `queued` 开始或终止；不得向 `AgentTask`、`TaskEvent` 增加任意 payload 字段。

- [ ] **步骤 4：验证并提交**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/task_center -q`  
预期：PASS。

```bash
git add iris_agent/task_center/models.py iris_agent/task_center/service.py tests/task_center/test_service.py && git commit -m "feat(任务中心): 支持排队任务状态"
```

### 任务 2：建立私有队列账本

**文件：** 创建 `iris_agent/task_queue/models.py`、`repository.py`、`__init__.py`；测试 `tests/task_queue/test_repository.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_repository_persists_fifo_and_rejects_invalid_payload(tmp_path):
    repo = QueueRepository(tmp_path)
    repo.save([QueueJob.new("task-1", "session-1", "完整用户消息")])
    assert repo.load()[0].message == "完整用户消息"
    path = tmp_path / "queue.json"
    path.write_text('{"jobs": ["invalid"]}', encoding="utf-8")
    with pytest.raises(QueueLedgerError):
        repo.load()
    assert path.read_text(encoding="utf-8") == '{"jobs": ["invalid"]}'
```

- [ ] **步骤 2：验证测试为红色**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/task_queue/test_repository.py -q`  
预期：FAIL，无法导入 `iris_agent.task_queue`。

- [ ] **步骤 3：实现作业与原子仓储**

```python
@dataclass(frozen=True, slots=True)
class QueueJob:
    task_id: str
    session_id: str
    message: str
    created_at: str
    state: Literal["queued", "active"] = "queued"

class QueueRepository:
    def load(self) -> list[QueueJob]: ...
    def save(self, jobs: list[QueueJob]) -> None: ...
```

复用 `TaskLedgerRepository` 的临时文件替换和 Windows 锁模式，账本数据固定写入 `queue.json`。允许同目录的内部 `queue.lock` 仅用于跨进程一字节文件锁；它不保存业务数据且不属于公开账本。只允许上述 5 个字段；拒绝未知状态及非字符串消息。

- [ ] **步骤 4：验证并提交**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/task_queue/test_repository.py -q`  
预期：PASS。

```bash
git add iris_agent/task_queue tests/task_queue/test_repository.py && git commit -m "feat(任务队列): 添加持久化作业账本"
```

### 任务 3：实现单工作者、审批与取消

**文件：** 创建 `iris_agent/task_queue/service.py`；测试 `tests/task_queue/test_service.py`。

- [ ] **步骤 1：编写 FIFO、审批和恢复失败测试**

```python
def test_waiting_approval_blocks_later_jobs_until_resolution(queue, provider):
    waiting = queue.submit("session-1", "write")
    later = queue.submit("session-2", "later")
    assert wait_until(lambda: queue.task_center.get_task(waiting.id).status == "awaiting_approval")
    assert queue.task_center.get_task(later.id).status == "queued"
    queue.resolve_approval(waiting.id, "write-1", approved=True)
    assert wait_until(lambda: queue.task_center.get_task(later.id).status == "completed")
    assert provider.max_in_flight == 1
```

- [ ] **步骤 2：验证测试为红色**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/task_queue/test_service.py -q`  
预期：FAIL，缺少 `TaskQueueService`。

- [ ] **步骤 3：实现协调服务**

```python
class TaskQueueService:
    def submit(self, session_id: str, message: str) -> AgentTask: ...
    def resolve_approval(self, task_id: str, call_id: str, approved: bool) -> AgentTask: ...
    def cancel(self, task_id: str) -> AgentTask: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def queue_position(self, task_id: str) -> int | None: ...
```

线程取得最早 `queued` 条目，改为 `active` 后调用 `task_center.start`。逐个消费 `AgentService` 事件：工具名与耗时进入任务中心，`text_delta` 仅触发 `touch`，回复文本绝不落盘。审批事件保存内存 `(task_id, call_id)` 并在条件变量等待；批准或拒绝后由同一线程调用 `resolve_tool_approval`，后续作业不得启动。取消队列条目时删除账本；取消待审批调用 `AgentService.cancel_tool_approval`；运行中任务在下一个事件前停止。终态删除 `active` 条目。

- [ ] **步骤 4：验证并提交**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/task_queue/test_service.py tests/task_center -q`  
预期：PASS。

```bash
git add iris_agent/task_queue/service.py tests/task_queue/test_service.py && git commit -m "feat(任务队列): 添加单工作者执行服务"
```

### 任务 4：接入设置、应用生命周期与 REST API

**文件：** 修改 `iris_agent/config/settings.py`、`agent.yaml`、`iris_agent/bootstrap.py`、`server.py`、`iris_agent/api/schemas.py`、`iris_agent/api/tasks_api.py`、`iris_agent/api/app.py`；创建 `tests/api/test_task_queue_api.py`。

- [ ] **步骤 1：编写 API 失败测试**

```python
def test_submit_returns_accepted_summary_without_message(client, session):
    response = client.post("/api/tasks", json={"session_id": session.id, "message": "私有问题"})
    assert response.status_code == 202
    assert response.json()["status"] in {"queued", "running"}
    assert "message" not in response.json()

def test_terminal_task_cannot_be_cancelled_or_approved(client, completed_task):
    assert client.delete(f"/api/tasks/{completed_task.id}").status_code == 409
    assert client.post(f"/api/tasks/{completed_task.id}/tool-approvals/call-1", json={"approved": True}).status_code == 409
```

- [ ] **步骤 2：验证测试为红色**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/api/test_task_queue_api.py -q`  
预期：FAIL，`POST /api/tasks` 返回 405 或 404。

- [ ] **步骤 3：实现配置、注入和路由**

```python
@dataclass(slots=True)
class TaskQueueSettings:
    directory: Path = Path("data/task_queue")

class QueueTaskRequest(BaseModel):
    session_id: str
    message: str

@router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_task(request: QueueTaskRequest):
    return _task_data(queue.submit(request.session_id, request.message))
```

将 `task_queue` 加到 `Settings`、`ApplicationServices`、`build_application` 和 `create_app` 的可选依赖中。`server.py` 的启动/关闭钩子调用 `task_queue.start()`、`task_queue.stop()`。任务中心路由接收队列服务，在摘要和详情中附加 `queue_position`；仅返回公共安全字段。保留现有流式聊天和审批路由，避免破坏旧 API。

- [ ] **步骤 4：验证并提交**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/api/test_task_queue_api.py tests/api/test_tasks_api.py tests/test_bootstrap_services.py -q`  
预期：PASS。

```bash
git add iris_agent/config/settings.py agent.yaml iris_agent/bootstrap.py server.py iris_agent/api/schemas.py iris_agent/api/tasks_api.py iris_agent/api/app.py tests/api/test_task_queue_api.py && git commit -m "feat(任务队列): 提供后台任务接口"
```

### 任务 5：改造前端提交、轮询和审批

**文件：** 修改 `web-react/src/types.ts`、`web-react/src/api/tasks.ts`、`web-react/src/hooks/useChat.ts`、`web-react/src/hooks/useChat.task.test.tsx`、`web-react/src/components/ChatContainer.tsx`、`web-react/src/components/ChatContainer.approval.test.tsx`。

- [ ] **步骤 1：编写 Hook 失败测试**

```tsx
it('submits a task, polls it, then refreshes the completed session', async () => {
  vi.mocked(createTask).mockResolvedValue({ ...task, status: 'queued' });
  vi.mocked(getTask).mockResolvedValueOnce({ ...task, status: 'running', events: [] })
    .mockResolvedValueOnce({ ...task, status: 'completed', events: [] });
  vi.mocked(getSession).mockResolvedValue({ messages: [{ role: 'assistant', content: '完成回复' }] });
  const { result } = renderHook(() => useChat());
  await act(async () => result.current.handleSendWithSession('开始'));
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(result.current.messages.at(-1)).toEqual({ role: 'assistant', content: '完成回复' });
  expect(streamChat).not.toHaveBeenCalled();
});
```

- [ ] **步骤 2：验证测试为红色**

运行：`$env:PATH='D:\agent\.tools\node-v24.19.0-win-x64;' + $env:PATH; & 'D:\agent\.tools\node-v24.19.0-win-x64\npm.cmd' test -- --run src/hooks/useChat.task.test.tsx`  
预期：FAIL，缺少 `createTask` 或轮询逻辑。

- [ ] **步骤 3：实现 API 类型和 Hook**

```ts
export type TaskStatus = 'queued' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'stopped';
export async function createTask(sessionId: string, message: string): Promise<AgentTask> { ... }
export async function cancelTask(id: string): Promise<AgentTask> { ... }
export async function resolveTaskApproval(id: string, callId: string, approved: boolean): Promise<AgentTask> { ... }
```

`useChat` 保存当前任务 ID 与状态，以 1 秒定时器查询详情。队列活跃时输入框保持可提交，让后续消息成为新的队列作业；`isStreaming` 改为仅表示当前聊天有未终态任务，不再作为输入禁用条件。`completed` 时调用 `getSession` 并停止对应任务的轮询；`failed`、`stopped` 显示安全 toast。切换会话、新建聊天、组件卸载和终态都清理定时器。保留 `streamingContent` 的组件兼容字段，但队列模式绝不写入文本增量。

- [ ] **步骤 4：实现聊天状态与审批、取消操作**

```tsx
{currentTaskStatus === 'queued' && <p className="chat-task-state">任务排队中…</p>}
{currentTaskStatus === 'running' && <p className="chat-task-state">正在执行任务…</p>}
<button onClick={() => onStop()}>停止任务</button>
```

审批按钮调用任务审批回调，并在请求中禁用；停止按钮调用任务取消回调。不要把 `pendingApproval.arguments` 或任务详情写入状态提示。

- [ ] **步骤 5：验证并提交**

运行：`$env:PATH='D:\agent\.tools\node-v24.19.0-win-x64;' + $env:PATH; & 'D:\agent\.tools\node-v24.19.0-win-x64\npm.cmd' test -- --run src/hooks/useChat.task.test.tsx src/components/ChatContainer.approval.test.tsx`  
预期：PASS。

```bash
git add web-react/src/types.ts web-react/src/api/tasks.ts web-react/src/hooks/useChat.ts web-react/src/hooks/useChat.task.test.tsx web-react/src/components/ChatContainer.tsx web-react/src/components/ChatContainer.approval.test.tsx && git commit -m "feat(聊天): 接入后台任务队列"
```

### 任务 6：完善任务中心展示并全量验证

**文件：** 修改 `web-react/src/components/tasks/TaskCenterPage.tsx`、`TaskCenterPage.test.tsx`、`web-react/src/App.tsx`、`App.test.tsx`、`App.css`。

- [ ] **步骤 1：编写页面失败测试**

```tsx
it('shows a queued task position and sends its cancellation request', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [{ ...task, status: 'queued', queue_position: 2 }] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ...task, status: 'queued', queue_position: 2, events: [] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ...task, status: 'stopped', events: [] }) }));
  render(<TaskCenterPage />);
  expect(await screen.findByText('队列第 2 位')).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: '取消任务' }));
  expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/tasks/task-1'), { method: 'DELETE' });
});
```

- [ ] **步骤 2：验证测试为红色**

运行：`$env:PATH='D:\agent\.tools\node-v24.19.0-win-x64;' + $env:PATH; & 'D:\agent\.tools\node-v24.19.0-win-x64\npm.cmd' test -- --run src/components/tasks/TaskCenterPage.test.tsx`  
预期：FAIL，未渲染队列位置或取消按钮。

- [ ] **步骤 3：实现展示与 App 接线**

```tsx
{detail.status === 'queued' && typeof detail.queue_position === 'number' && <p>队列第 {detail.queue_position} 位</p>}
{['queued', 'running', 'awaiting_approval'].includes(detail.status) && <button onClick={() => void cancelTask(detail.id)}>取消任务</button>}
```

新增 `.status-queued`、`.chat-task-state` 与任务操作按钮的 Iris 主题和小屏样式。`App` 持续把“查看任务”的 ID 传入任务中心，并更新 mocked `useChat` 返回值。

- [ ] **步骤 4：运行局部前端测试与构建**

运行：`$env:PATH='D:\agent\.tools\node-v24.19.0-win-x64;' + $env:PATH; & 'D:\agent\.tools\node-v24.19.0-win-x64\npm.cmd' test -- --run src/components/tasks/TaskCenterPage.test.tsx src/App.test.tsx`  
预期：PASS。

运行：`$env:PATH='D:\agent\.tools\node-v24.19.0-win-x64;' + $env:PATH; & 'D:\agent\.tools\node-v24.19.0-win-x64\npm.cmd' run build`  
预期：Vite 生产构建成功。

- [ ] **步骤 5：全量验证并提交**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest -q`  
预期：所有后端测试通过。

运行：`$env:PATH='D:\agent\.tools\node-v24.19.0-win-x64;' + $env:PATH; & 'D:\agent\.tools\node-v24.19.0-win-x64\npm.cmd' test -- --run`  
预期：所有前端测试通过。

```bash
git add web-react/src/components/tasks/TaskCenterPage.tsx web-react/src/components/tasks/TaskCenterPage.test.tsx web-react/src/App.tsx web-react/src/App.test.tsx web-react/src/App.css && git commit -m "feat(任务中心): 展示队列状态与取消入口"
```

## 计划自检

- 规格覆盖：任务 1 覆盖 `queued`；任务 2 覆盖独立账本；任务 3 覆盖单工作者、审批、取消与重启；任务 4 覆盖 API 与生命周期；任务 5 覆盖完成后回填；任务 6 覆盖任务中心和全量验证。
- 类型一致性：后端统一使用 `TaskQueueService.submit`、`resolve_approval`、`cancel`、`queue_position`；前端统一使用 `TaskStatus` 和 `queue_position`。
- 安全边界：完整用户消息只在私有队列账本存在；任务中心模型、任务 API 和前端详情均不显示该字段，也不加入工具参数、结果、环境变量、模型回复或原始异常。
