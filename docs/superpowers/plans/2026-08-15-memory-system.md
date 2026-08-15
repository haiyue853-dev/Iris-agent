# 记忆系统一期实现计划（P1）

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans`（或 `subagent-driven-development`）逐任务实现。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 让 Iris 跨会话记住用户关键信息，并在每次对话开始时把相关记忆注入系统提示。

**架构：** 新增 `iris_agent/memory/` 负责记忆模型、原子 JSON 账本与注入选择；`AgentService` 在组装 messages 时注入记忆；`remember` 工具让 Agent 主动保存；`MemoryService` 接入装配与 REST API；前端新增记忆页面。

**技术栈：** Python 3、FastAPI、原子 JSON 仓储、Pytest、React、TypeScript、Vitest。

**工作目录：** 所有命令在 `D:\agent\iris-agent` 下执行（后端测试用 `D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=<全新目录>` 以绕过本机损坏的 pytest 临时目录）。

---

### 任务 1：记忆模型与原子账本

**文件：** 创建 `iris_agent/memory/__init__.py`、`models.py`、`repository.py`；测试 `tests/memory/test_repository.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_repository_roundtrips_and_rejects_invalid_entry(tmp_path):
    repo = MemoryRepository(tmp_path)
    repo.save([MemoryEntry.new("用户偏好中文回答", "preference")])
    assert repo.load()[0].content == "用户偏好中文回答"
    assert repo.load()[0].category == "preference"

def test_entry_validation_rejects_bad_category_and_blank_content():
    with pytest.raises(ValueError):
        MemoryEntry.new("", "fact")
    with pytest.raises(ValueError):
        MemoryEntry.new("内容", "unknown")
```

- [ ] **步骤 2：验证为红色**

运行：`D:/agent/iris-agent/.venv/Scripts/python.exe -m pytest tests/memory/test_repository.py -q -p no:cacheprovider`  
预期：FAIL，无法导入 `iris_agent.memory`。

- [ ] **步骤 3：实现模型与仓储**

`models.py`：

```python
@dataclass(frozen=True, slots=True)
class MemoryEntry:
    id: str
    content: str
    category: str
    created_at: str
    updated_at: str
    source_session_id: str | None = None

    @classmethod
    def new(cls, content: str, category: str, source_session_id: str | None = None) -> "MemoryEntry": ...

    def __post_init__(self):  # 校验白名单 category、1-500 非空白 content
```

`repository.py`：`MemoryRepository.load() -> list[MemoryEntry]`、`save(entries) -> None`，复用 `task_queue/repository.py` 的原子写 + Windows 一字节锁，账本固定 `memory.json`，结构 `{"entries": [...]}`。

- [ ] **步骤 4：验证并提交**

运行：`... pytest tests/memory/test_repository.py -q -p no:cacheprovider` → PASS。

```bash
git add iris_agent/memory tests/memory/test_repository.py && git commit -m "feat(记忆): 添加记忆模型与原子账本"
```

---

### 任务 2：记忆服务与注入选择

**文件：** 创建 `iris_agent/memory/service.py`；测试 `tests/memory/test_service.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_add_list_delete_and_inject_limits(service):
    for i in range(25):
        service.add(f"事实 {i}", "fact")
    assert len(service.list()) == 20  # max_entries 淘汰
    assert service.add("", "fact") raises ValueError

def test_inject_respects_char_and_entry_caps(service):
    service.add("用户偏好中文" * 10, "preference")
    injected = service.inject()
    assert sum(len(m.content) for m in injected) <= 2000
```

- [ ] **步骤 2：验证为红色**

运行：`... pytest tests/memory/test_service.py -q -p no:cacheprovider` → FAIL。

- [ ] **步骤 3：实现服务**

```python
class MemoryService:
    def __init__(self, repository, max_entries=500, max_chars=500, max_injected_chars=2000, max_injected_entries=20): ...
    def add(self, content, category, source_session_id=None) -> MemoryEntry: ...
    def list(self) -> list[MemoryEntry]: ...
    def delete(self, entry_id) -> None: ...
    def inject(self) -> list[MemoryEntry]: ...
```

`add` 校验后写入并淘汰超限旧条目；`inject` 按 `updated_at` 倒序，累计字符/条数不超上限。

- [ ] **步骤 4：验证并提交**

运行：`... pytest tests/memory/test_service.py -q -p no:cacheprovider` → PASS。

```bash
git add iris_agent/memory/service.py tests/memory/test_service.py && git commit -m "feat(记忆): 添加记忆服务与注入选择"
```

---

### 任务 3：remember 工具与 AgentService 注入

**文件：** 创建 `iris_agent/tools/builtin/memory_tool.py`；修改 `iris_agent/core/agent.py`；测试 `tests/test_agent_memory_injection.py`、`tests/tools/test_memory_tool.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_agent_injects_memory_into_system_messages(memory_service, provider, registry):
    memory_service.add("用户偏好中文", "preference")
    agent = AgentService(loop, sessions, "base prompt", memory=memory_service)
    # 触发 run 并断言 provider.complete 收到的 messages 含 "[记忆·preference] 用户偏好中文"
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现注入与工具**

`core/agent.py`：

```python
def __init__(self, loop, sessions, system_prompt, memory=None):
    ...
    self.memory = memory

def _build_messages(self, session):
    messages = [Message(role="system", content=self.system_prompt)]
    if self.memory is not None:
        for m in self.memory.inject():
            messages.append(Message(role="system", content=f"[记忆·{m.category}] {m.content}"))
    messages.extend(session.messages)
    return messages
```

`run()` 与 `resolve_tool_approval()` 改用 `self._build_messages(session)`。

`memory_tool.py`：`build_remember_tool(memory)`，`requires_approval=False`，参数 `content`（必填）、`category`（可选默认 `fact`）。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/tools/builtin/memory_tool.py iris_agent/core/agent.py tests/ && git commit -m "feat(记忆): Agent 注入记忆并提供 remember 工具"
```

---

### 任务 4：配置、装配与 REST API

**文件：** 修改 `iris_agent/config/settings.py`、`agent.yaml`、`iris_agent/bootstrap.py`、`iris_agent/api/app.py`；创建 `iris_agent/api/memory_api.py`；测试 `tests/api/test_memory_api.py`、`tests/test_bootstrap_services.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_memory_crud_api(client):
    created = client.post("/api/memory", json={"content": "用户偏好中文", "category": "preference"})
    assert created.status_code == 200
    assert client.get("/api/memory").json()["entries"][0]["content"] == "用户偏好中文"
    assert client.delete(f"/api/memory/{created.json()['id']}").status_code == 200
```

- [ ] **步骤 2：验证为红色** → FAIL（404）。

- [ ] **步骤 3：实现配置、装配与路由**

`settings.py` 加 `MemorySettings` + `_section` 加载；`bootstrap.py` 构造 `MemoryService`、注册 `build_remember_tool`、传给 `AgentService`；`memory_api.py` 注册 `GET/POST/DELETE /api/memory` 路由。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/config/settings.py agent.yaml iris_agent/bootstrap.py iris_agent/api/ tests/ && git commit -m "feat(记忆): 接入配置、装配与记忆 API"
```

---

### 任务 5：前端记忆页面

**文件：** 创建 `web-react/src/api/memory.ts`、`web-react/src/components/memory/MemoryPage.tsx` 及测试；修改 `web-react/src/App.tsx`、`web-react/src/components/Sidebar.tsx`、`App.css`。

- [ ] **步骤 1：编写失败测试**

```tsx
it('lists, adds, and deletes memories', async () => {
  vi.stubGlobal('fetch', ...);
  render(<MemoryPage />);
  expect(await screen.findByText('用户偏好中文')).toBeInTheDocument();
  // 添加、删除交互断言
});
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现页面与导航**

`MemoryPage` 展示记忆列表（内容 + 类别徽标 + 时间）、添加表单、删除按钮；`App.tsx` 增加 `memory` 视图并接入侧栏。

- [ ] **步骤 4：验证并提交**

运行：`npm test -- src/components/memory/MemoryPage.test.tsx` → PASS；`npm run build` 通过。

```bash
git add web-react/src/ && git commit -m "feat(记忆): 添加记忆管理页面"
```

---

### 任务 6：全量验证

- [ ] **步骤 1：后端全量** `... pytest -q -p no:cacheprovider --basetemp=<全新目录>` → 通过（新增记忆用例）。
- [ ] **步骤 2：前端全量** `npm test` → 通过；`npm run build` → 通过。
- [ ] **步骤 3：隐私核对** 记忆账本仅白名单字段；接口不泄露账本路径/原始异常；工具不存敏感 payload。

---

## 计划自检

- 规格覆盖：任务 1 覆盖模型与账本；任务 2 覆盖注入选择与上限；任务 3 覆盖 Agent 注入与主动记忆工具；任务 4 覆盖配置/装配/API；任务 5 覆盖前端；任务 6 覆盖全量验证。
- 类型一致性：后端统一 `MemoryService.add/list/delete/inject`；前端 `MemoryEntry` 与后端白名单字段一致。
- 安全边界：`remember` 工具与 API 只接受 `content`/`category`，不触碰工具参数、结果、环境变量或密钥；注入仅追加 `system` 消息，不改动 `AgentLoop` 语义。

---

## 执行记录（2026-08-15）

六个任务全部完成并提交，分支 `feature/memory-system`：

1. `feat(记忆): 添加记忆模型与原子账本` —— `memory/models.py`、`repository.py`（复用 task_queue 原子写 + Windows 一字节锁），8 条测试。
2. `feat(记忆): 添加记忆服务与注入选择` —— `memory/service.py`（add/list/delete/inject，max_entries 淘汰、注入字符/条数上限），8 条测试。
3. `feat(记忆): Agent 注入记忆并提供 remember 工具` —— `AgentService` 加 `memory` 参数 + `_build_messages`；`build_remember_tool`（`requires_approval=False`），7 条测试。
4. `feat(记忆): 接入配置、装配与记忆 API` —— `MemorySettings`、`bootstrap.py` 装配、`memory_api.py`、`create_app` 注册、`server.py`、`agent.yaml`，9 条测试。
5. `feat(记忆): 添加记忆管理页面与导航` —— `MemoryPage`、`api/memory.ts`、`App.tsx`/`Sidebar`/`App.css` 接线，3 条测试。
6. 全量验证：后端 `344 passed, 1 failed, 2 skipped`（唯一失败为已知环境问题 `test_rejects_external_attachments_directory_symlink_during_load`，Python 3.14.5 在 Windows 的 `os.symlink` 行为异常，与记忆系统无关）；前端 `112 passed`、`npm run build` 通过。

环境备注：memory-system 为新 worktree，`web-react/node_modules` 以 Windows junction 复用 main 的依赖（避免重新安装）；后端测试需 `-p no:cacheprovider --basetemp=<全新目录>` 绕过本机损坏的 pytest 临时目录。

