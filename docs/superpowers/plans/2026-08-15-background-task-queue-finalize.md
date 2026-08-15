# 后台任务队列收尾实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法跟踪进度。

**目标：** 完成后台任务队列一期的任务中心页面展示（队列位置 + 取消入口）、全量验证与分支合并。

**架构：** 在现有 `TaskCenterPage` 详情区补充排队位置与取消入口，复用已就绪的后端 `queue_position` 字段与前端 `cancelTask` 客户端；随后执行全量后端/前端验证，最后推送并合并 `feature/background-task-queue`。

**技术栈：** Python 3、FastAPI、Pytest、React、TypeScript、Vitest、Vite。

**工作目录：** 所有命令在 worktree `D:\agent\iris-agent\.worktrees\background-task-queue` 下执行。

---

## 前置：环境核对（已确认）

- 后端解释器：`D:\agent\iris-agent\.venv\Scripts\python.exe`（pytest 9.1.1、fastapi 0.141.1 已装）
- 前端：`web-react/node_modules` 已装；`npm` 10.9.7、`node` v22.22.2 可用
- 前端测试脚本：`package.json` 中 `"test": "vitest run"`；构建 `"build": "tsc -b && vite build"`

---

### 任务 1：Task 5 收尾复审（`094aa88`）

**文件：** 只读，不修改。

- [ ] **步骤 1：读取 `094aa88` 提交差异**

运行：`git -C D:/agent/iris-agent/.worktrees/background-task-queue show 094aa88 --stat` 及 `git -C ... show 094aa88`

- [ ] **步骤 2：规格复审**

对照 `docs/superpowers/specs/2026-08-14-background-task-queue-design.md` 逐条核对：删除会话后是否停止对应任务轮询、清理任务状态；切换会话/新建聊天/组件卸载时轮询生命周期是否完整；`useChat` 是否不写入文本增量；审批仅在服务端返回 `approval_call_id` 时展示。

- [ ] **步骤 3：独立代码质量复审**

核对：隐私边界（用户消息、工具参数、返回值、原始异常不进入任务中心或前端状态）；竞态与单飞保护；定时器清理是否覆盖所有退出路径。

- [ ] **步骤 4：输出复审结论**

结论为「通过」则 Task 5 正式收尾；发现缺陷则在任务 2 之前以 TDD 修复并补充回归测试。复审结论写入本计划的进度备注，不另建文件。

---

### 任务 2：任务中心页展示队列位置与取消入口（TDD）

**文件：**
- Modify: `web-react/src/components/tasks/TaskCenterPage.tsx`
- Modify: `web-react/src/components/tasks/TaskCenterPage.test.tsx`
- Modify: `web-react/src/App.css`

- [ ] **步骤 1：编写失败测试**

在 `TaskCenterPage.test.tsx` 末尾的 `describe` 内追加：

```tsx
it('shows a queued task position and sends its cancellation request', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ tasks: [{ ...task, status: 'queued', queue_position: 2 }] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ...task, status: 'queued', queue_position: 2, events: [] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ...task, status: 'stopped', events: [] }) });
  vi.stubGlobal('fetch', fetchMock);
  const user = userEvent.setup();

  render(<TaskCenterPage />);

  expect(await screen.findByText('队列第 2 位')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '取消任务' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  expect(fetchMock).toHaveBeenLastCalledWith(
    expect.stringContaining('/api/tasks/task-1'),
    { method: 'DELETE' },
  );
});
```

- [ ] **步骤 2：验证测试为红色**

运行：`cd D:/agent/iris-agent/.worktrees/background-task-queue/web-react && npm test -- src/components/tasks/TaskCenterPage.test.tsx`  
预期：FAIL，未渲染「队列第 2 位」或「取消任务」按钮。

- [ ] **步骤 3：实现页面逻辑**

`TaskCenterPage.tsx`：

```tsx
import { cancelTask, getTask, listTasks } from '../../api/tasks';
```

组件内新增：

```tsx
const [cancellingId, setCancellingId] = useState<string | null>(null);

const cancel = async (taskId: string) => {
  setCancellingId(taskId);
  try {
    const cancelled = await cancelTask(taskId);
    setDetail(cancelled);
    setTasks((prev) => prev.map((t) => (t.id === taskId ? cancelled : t)));
  } catch {
    setDetailError(true);
  } finally {
    setCancellingId(null);
  }
};
```

详情区渲染，在状态徽章后追加：

```tsx
{detail.status === 'queued' && typeof detail.queue_position === 'number' && (
  <p className="task-queue-position">队列第 {detail.queue_position} 位</p>
)}
{['queued', 'running', 'awaiting_approval'].includes(detail.status) && (
  <button className="task-cancel-btn" disabled={cancellingId === detail.id} onClick={() => void cancel(detail.id)}>
    {cancellingId === detail.id ? '取消中…' : '取消任务'}
  </button>
)}
```

注意：取消后仅用返回结果就地更新 `detail` 与 `tasks`，**不再触发列表/详情加载**，避免改变 fetch 调用顺序。

- [ ] **步骤 4：验证测试为绿色**

运行：`cd .../web-react && npm test -- src/components/tasks/TaskCenterPage.test.tsx`  
预期：PASS（含新增用例）。

- [ ] **步骤 5：补充样式并提交**

`App.css` 追加（紧随现有 `.status-stopped` 之后）：

```css
.status-queued { color: #7a5af8; }
.task-queue-position { margin: 0; color: var(--iris-accent); font-size: 13px; font-weight: 600; }
.task-cancel-btn { padding: 7px 12px; border: 1px solid #d87b7b; border-radius: 8px; background: #fff3f3; color: #a33b3b; cursor: pointer; }
.task-cancel-btn:disabled { opacity: .6; cursor: default; }
```

```bash
cd D:/agent/iris-agent/.worktrees/background-task-queue
git add web-react/src/components/tasks/TaskCenterPage.tsx web-react/src/components/tasks/TaskCenterPage.test.tsx web-react/src/App.css
git commit -m "feat(任务中心): 展示队列位置与取消入口"
```

---

### 任务 3：全量验证

- [ ] **步骤 1：后端全量测试**

运行：`cd D:/agent/iris-agent/.worktrees/background-task-queue && D:/agent/iris-agent/.venv/Scripts/python.exe -m pytest -q`  
预期：全部通过（基线约 `316 passed, 3 skipped`）。

- [ ] **步骤 2：前端全量测试**

运行：`cd .../web-react && npm test`  
预期：全部通过（基线 `106/106` 之上新增 1 条）。

- [ ] **步骤 3：前端生产构建**

运行：`cd .../web-react && npm run build`  
预期：`tsc -b` 与 `vite build` 均成功。

- [ ] **步骤 4：隐私边界与跨会话核对**

人工核对：队列账本仅含五字段；任务 API/前端不含用户消息、工具参数/结果、环境变量、模型原文、原始异常；切会话/新建/删除会话后轮询与活动任务状态正确清理。

---

### 任务 4：推送并合并

- [ ] **步骤 1：整理变更记录**

在 `PROJECT_STATUS_2026-08-15.md` 中把任务 6、全量验证、复审结论更新为已完成，并把「下一步建议」指向合并。

- [ ] **步骤 2：推送分支**

运行：`git -C D:/agent/iris-agent/.worktrees/background-task-queue push -u origin feature/background-task-queue`

- [ ] **步骤 3：合并到 main（待用户确认）**

合并动作（`git merge feature/background-task-queue` 到 `main`，或走 PR）**仅在用户确认后执行**。

---

## 计划自检

- 规格覆盖：任务 1 覆盖 `094aa88` 复审；任务 2 覆盖设计文档「前端体验」中任务中心队列位置与取消入口；任务 3 覆盖验收标准中的全量验证与隐私核对；任务 4 覆盖收尾合并。
- 类型一致性：后端 `queue_position` 字段、前端 `AgentTask.queue_position?: number | null`、`cancelTask(id)` 均已存在，无需改动 API 契约。
- 安全边界：新增 UI 仅读取 `queue_position` 与 `status`，不触碰用户消息、工具参数或事件中任何敏感字段。

---

## 执行记录（2026-08-15）

### 任务 1：`094aa88` 复审结论 —— 通过

- 规格：删除会话清理轮询与任务状态、切换会话竞态保护、toast 按会话隔离、不写入文本增量，均符合设计文档。
- 质量：`discardSessionTasks` / `clearCurrentTaskState` / `sessionSwitchRequestRef` 实现清晰；轮询清理覆盖终态、切会话、删除会话、新建、卸载各路径；无隐私边界问题。对应测试 `useChat.task.test.tsx` 11 条全绿。

### 任务 2：任务中心页 —— 已完成（提交 `5f4dc1a`）

- 新增「队列第 N 位」展示与「取消任务」按钮，测试先行（5/5 绿），补充 `.status-queued` / `.task-queue-position` / `.task-cancel-btn` 样式。
- 顺带修正 `cancelTask` 返回类型为 `TaskDetail`（后端取消接口本就返回 `include_events=True`），并同步修复 `useChat.task.test.tsx` 3 处 mock 类型。

### 任务 3：全量验证结果

- 后端：`316 passed, 1 failed, 2 skipped`（与基线 `316 passed, 3 skipped` 通过数一致）。
- 前端：`109 passed`（22 个文件）；`npm run build`（tsc + vite）通过。
- 后端唯一失败 `test_rejects_external_attachments_directory_symlink_during_load` 为**环境问题**：本机 Python 3.14.5 在 Windows 下 `os.symlink(..., target_is_directory=True)` 异常返回成功但实际创建普通目录（`st_reparse_tag=0`），导致 `Path.resolve()` 无法解析符号链接、防护断言 `DID NOT RAISE`。该测试文件相对 `main` 零改动，与本次前端改动无关，不影响合并。
- 环境备注：本机 `%TEMP%\pytest-of-zhb` 与 worktree `.pytest_cache\v\cache` 目录 ACL 损坏（拒绝访问），需以 `-p no:cacheprovider --basetemp=<全新目录>` 运行后端测试。

### 任务 4：推送并合并 —— 见 git 提交与分支状态。

