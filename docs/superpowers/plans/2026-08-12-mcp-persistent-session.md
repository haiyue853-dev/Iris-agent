# MCP 持久 stdio 会话实现计划

> **面向 AI 代理的工作者：** 必须按测试先行方式逐项实现并验证。

**目标：** 让同一 MCP 服务在连续工具调用间复用 stdio 子进程，从而保持 Browser MCP 的浏览器页面状态。

**架构：** `McpCenterService` 维护按服务 ID 索引的进程会话；会话在首次发现或调用时初始化，后续 `tools/list` 与 `tools/call` 复用同一 stdin/stdout。停用、删除、调用异常和应用关闭时终止对应子进程。现有白名单、工具注册和审批规则不变。

**技术栈：** Python 3.14、FastAPI、JSON-RPC 2.0 stdio、pytest。

---

### 任务 1：持久会话与请求复用

**文件：**

- 修改：`iris_agent/mcp_center/service.py`
- 测试：`tests/mcp/test_mcp_center_service.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_two_mcp_calls_reuse_one_initialized_process(tmp_path, monkeypatch):
    service, server = enabled_service(tmp_path)
    process = fake_process_with_responses()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

    service.call_tool(server.id, "navigate", {"url": "https://example.test"})
    service.call_tool(server.id, "get_page_source", {})

    assert process.starts == 1
    assert process.call_names == ["navigate", "get_page_source"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/mcp/test_mcp_center_service.py::test_two_mcp_calls_reuse_one_initialized_process -q`

预期：失败，当前实现为每次调用创建新进程。

- [ ] **步骤 3：实现最小持久会话层**

```python
def _session(self, server: McpServer) -> _McpProcessSession:
    session = self._sessions.get(server.id)
    if session is None or session.ended:
        session = _McpProcessSession.start(self._command_args(server), self._subprocess_env(server))
        self._sessions[server.id] = session
    return session
```

会话完成 initialize 后递增 JSON-RPC 请求 ID；`discover_tools` 与 `call_tool` 都从该会话请求数据。

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/mcp/test_mcp_center_service.py -q`

预期：所有 MCP 服务测试通过。

### 任务 2：回收与故障隔离

**文件：**

- 修改：`iris_agent/mcp_center/service.py`
- 测试：`tests/mcp/test_mcp_center_service.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_disabling_or_deleting_server_closes_its_live_session(tmp_path, monkeypatch):
    service, server, process = live_service(tmp_path, monkeypatch)
    service.set_enabled(server.id, False)
    assert process.terminated is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/mcp/test_mcp_center_service.py::test_disabling_or_deleting_server_closes_its_live_session -q`

预期：失败，没有会话回收行为。

- [ ] **步骤 3：实现回收与故障后丢弃会话**

```python
def _close_session(self, server_id: str) -> None:
    session = self._sessions.pop(server_id, None)
    if session is not None:
        session.close()
```

`set_enabled(False)`、`delete()` 调用该方法；请求失败时关闭并从字典移除会话，下一次调用才可重建。

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/mcp/test_mcp_center_service.py -q`

预期：所有 MCP 服务测试通过。

### 任务 3：刷新与启动边界回归

**文件：**

- 修改：`iris_agent/mcp_center/tools.py`（仅在测试发现必要时）
- 测试：`tests/mcp/test_runtime.py`、`tests/test_bootstrap_services.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_refresh_uses_the_live_session_for_discovery(tmp_path, monkeypatch):
    service, server = enabled_service(tmp_path)
    # 同一进程返回 tools/list，刷新不会额外启动进程
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/mcp/test_runtime.py -q`

预期：若刷新绕过新会话层，测试失败。

- [ ] **步骤 3：只修正必要调用点**

保持应用启动仅读取缓存；显式检测和运行时刷新使用活连接，且刷新失败不会清空旧注册工具。

- [ ] **步骤 4：运行定向回归**

运行：`pytest tests/mcp/test_runtime.py tests/api/test_mcp_api.py tests/test_bootstrap_services.py -q`

预期：全部通过。

### 任务 4：真实 Browser MCP 连续调用与全量验证

**文件：**

- 修改：`tests/mcp/test_mcp_center_service.py`（如需协议测试夹具）

- [ ] **步骤 1：执行真实连续调用检查**

运行：通过 `McpCenterService` 调用 Browser MCP 的 `navigate`，再调用 `get_page_source`。

预期：第二个调用返回已导航页面的内容，且只启动一个 Node MCP 进程。

- [ ] **步骤 2：运行全量验证**

运行：`pytest -q --basetemp .pytest_tmp/mcp-persistent-final -p no:cacheprovider`、`npm run test`、`npm run build`。

预期：后端与前端回归通过；保留既有大包体构建警告。

- [ ] **步骤 3：提交**

```bash
git add iris_agent/mcp_center/service.py iris_agent/mcp_center/tools.py tests/mcp tests/api/test_mcp_api.py tests/test_bootstrap_services.py
git commit -m "feat: 复用 MCP 持久会话"
```
