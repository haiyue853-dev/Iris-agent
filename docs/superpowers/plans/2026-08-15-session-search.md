# 会话搜索召回一期实现计划（P2）

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans`（或 `subagent-driven-development`）逐任务实现。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 让 Iris 能通过 `recall` 工具检索并引用历史会话。

**架构：** 新增 `iris_agent/session_search/`（分词、命中模型、搜索服务）；`recall` 工具让 Agent 主动召回；`GET /api/search` 供前端/外部查询；搜索只读 user/assistant 文本，不持久化索引。

**技术栈：** Python 3、FastAPI、Pytest。

**工作目录：** `D:\agent\iris-agent`（后端测试用 `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=<全新目录>`）。

---

### 任务 1：分词器与命中模型

**文件：** 创建 `iris_agent/session_search/__init__.py`、`tokenizer.py`、`models.py`；测试 `tests/session_search/test_tokenizer.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_tokenize_chinese_bigrams_and_english_words():
    tokens = tokenize("聊聊项目 Python")
    assert "聊聊" in tokens and "项目" in tokens and "python" in tokens

def test_tokenize_is_case_insensitive_and_dedupes():
    assert tokenize("Hello hello") == {"hello"}

def test_search_hit_truncates_long_content():
    hit = SearchHit("session_x", "会话", "user", "长" * 400, 1.0, 5)
    assert len(hit.to_dict()["content"]) <= 300
```

- [ ] **步骤 2：验证为红色** → FAIL（无法导入）。

- [ ] **步骤 3：实现分词与模型**

`tokenizer.py`：中文连续二字 bigram + 英文小写 word，返回去重的 `set[str]`。
`models.py`：`SearchHit` dataclass + `to_dict()`，content 截断到 `max_hit_chars`。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/session_search tests/session_search/test_tokenizer.py && git commit -m "feat(搜索): 添加分词器与会话命中模型"
```

---

### 任务 2：搜索服务

**文件：** 创建 `iris_agent/session_search/service.py`；测试 `tests/session_search/test_service.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_search_returns_ranked_hits(repository):
    s1 = repository.create("项目讨论")
    repository.append(s1.id, Message(role="user", content="聊聊项目进展"))
    search = SessionSearchService(repository)
    hits = search.search("项目进展")
    assert hits[0].session_id == s1.id
    assert hits[0].content == "聊聊项目进展"

def test_search_skips_tool_messages_and_empty(repository):
    s1 = repository.create("空会话")
    repository.append(s1.id, Message(role="tool", content="机密参数"))
    search = SessionSearchService(repository)
    assert search.search("机密") == []
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现服务**

`service.py`：`search(query, limit=5)` 扫描 `sessions.list()`，对每条 user/assistant 非空消息计算 `score = len(query_tokens ∩ message_tokens)`，`score>0` 的按 score 降序、updated_at 降序取前 limit。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/session_search/service.py tests/session_search/test_service.py && git commit -m "feat(搜索): 添加会话搜索服务"
```

---

### 任务 3：recall 工具

**文件：** 创建 `iris_agent/tools/builtin/recall_tool.py`；测试 `tests/tools/test_recall_tool.py`；修改 `tools/builtin/__init__.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_recall_tool_returns_hits(search):
    tool = build_recall_tool(search)
    result = tool.invoke({"query": "项目"})
    assert result.ok
    assert isinstance(result.value["hits"], list)
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现工具**

`recall_tool.py`：`build_recall_tool(search)`，`requires_approval=False`，参数 `query`（必填）；返回 `{"hits": [hit.to_dict() ...]}`。`__init__.py` 导出 `build_recall_tool`。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/tools/builtin/recall_tool.py iris_agent/tools/builtin/__init__.py tests/tools/test_recall_tool.py && git commit -m "feat(搜索): 提供 recall 召回工具"
```

---

### 任务 4：配置、装配与搜索 API

**文件：** 修改 `iris_agent/config/settings.py`、`agent.yaml`、`iris_agent/bootstrap.py`、`iris_agent/api/app.py`；创建 `iris_agent/api/search_api.py`；测试 `tests/api/test_search_api.py`、`tests/test_bootstrap_services.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_search_api_returns_hits(client):
    response = client.get("/api/search", params={"query": "项目"})
    assert response.status_code == 200
    assert "hits" in response.json()
```

- [ ] **步骤 2：验证为红色** → FAIL（404）。

- [ ] **步骤 3：实现配置、装配与路由**

`settings.py` 加 `SessionSearchSettings`；`bootstrap.py` 构造 `SessionSearchService`、注册 `build_recall_tool`、装配；`search_api.py` 注册 `GET /api/search`；`app.py` 注册路由。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/config/settings.py agent.yaml iris_agent/bootstrap.py iris_agent/api/ tests/ && git commit -m "feat(搜索): 接入配置、装配与搜索 API"
```

---

### 任务 5：全量验证

- [ ] **步骤 1：后端全量** `pytest -q -p no:cacheprovider --basetemp=<全新目录>` → 通过（新增搜索用例）。
- [ ] **步骤 2：隐私核对** 搜索只返回 user/assistant 文本，`tool` 消息/工具参数/结果/密钥不出现。

---

## 计划自检

- 规格覆盖：任务 1 覆盖分词与命中模型；任务 2 覆盖搜索服务与排序；任务 3 覆盖 recall 工具；任务 4 覆盖配置/装配/API；任务 5 覆盖全量验证。
- 类型一致性：后端统一 `SessionSearchService.search`、`SearchHit.to_dict`；工具与 API 复用同一命中结构。
- 安全边界：仅搜索 user/assistant 文本，跳过 `tool` 消息；命中截断；`recall` 只读不写。

---

## 执行记录（2026-08-15）

五个任务全部完成并提交，分支 `feature/session-search`：

1. `feat(搜索): 添加分词器与会话命中模型` —— `tokenizer.py`（中文 bigram + 英文 word）、`models.py`（SearchHit），5 条测试。
2. `feat(搜索): 添加会话搜索服务` —— `service.py`（扫描会话 + 按 score/updated_at 排序 + limit），4 条测试。
3. `feat(搜索): 提供 recall 召回工具` —— `recall_tool.py`（`requires_approval=False`），3 条测试。
4. `feat(搜索): 接入配置、装配与搜索 API` —— `SessionSearchSettings`、`bootstrap.py` 装配、`search_api.py`、`create_app`/`server.py`、`agent.yaml`，4 条测试。
5. 全量验证：后端 `360 passed, 3 skipped, 0 failed`（Python 3.13 下全绿）；隐私核对通过（仅搜 user/assistant 文本、跳过 tool 消息、命中截断）。

