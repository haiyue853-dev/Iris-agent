# Tavily 联网搜索增强实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Tavily 接入为首选搜索源，保留现有免费回退，并提供可复用的深度联网研究 Skill。

**架构：** 各搜索源实现统一的 `search(query, limit, options)` 协议；聚合客户端依次回退并统一去重。Tavily 密钥来自环境变量，高级筛选通过现有 `web_search` 工具透传，复杂查询规划留给内置 Skill。

**技术栈：** Python 3.11+、httpx、dataclasses、pytest、YAML、Iris Skill Center

---

## 文件结构

- 修改 `iris_agent/web_search/models.py`：扩展结果元数据并定义搜索选项。
- 修改 `iris_agent/web_search/sources.py`：增加 Tavily 源并让现有源接受统一选项。
- 修改 `iris_agent/web_search/search.py`：实现高级参数透传、回退与 URL 去重。
- 修改 `iris_agent/tools/builtin/web_tools.py`：扩展工具 schema 和参数转发。
- 修改 `iris_agent/config/settings.py`：读取 Tavily 配置与 `TAVILY_API_KEY`。
- 修改 `iris_agent/bootstrap.py`：按密钥和开关装配搜索源顺序。
- 修改 `agent.yaml`、`.env.example`、`README.md`：提供非敏感配置说明。
- 创建 `iris_agent/skill_center/bundled/web-research/SKILL.md`：定义多轮研究流程。
- 修改对应 `tests/` 文件：覆盖模型、源、聚合、工具、配置、装配及技能发现。

### 任务 1：扩展统一搜索模型

**文件：**
- 修改：`iris_agent/web_search/models.py`
- 测试：`tests/web_search/test_search.py`

- [ ] **步骤 1：编写失败的元数据与选项测试**

```python
def test_search_result_serializes_available_metadata():
    result = SearchResult(
        title="标题", url="https://example.com", snippet="摘要",
        source="tavily", published_date="2026-08-22", score=0.91,
    )
    assert result.to_dict()["source"] == "tavily"
    assert result.to_dict()["published_date"] == "2026-08-22"

def test_search_options_rejects_too_many_domains():
    with pytest.raises(ValueError):
        SearchOptions(include_domains=tuple(f"d{i}.com" for i in range(21)))
```

- [ ] **步骤 2：运行测试并确认因新类型不存在而失败**

运行：`python -m pytest tests/web_search/test_search.py -q`
预期：FAIL，指出 `SearchOptions` 或新增字段不存在。

- [ ] **步骤 3：实现兼容的数据类型**

```python
@dataclass(frozen=True, slots=True)
class SearchOptions:
    topic: str = "general"
    time_range: str | None = None
    include_domains: tuple[str, ...] = ()
    exclude_domains: tuple[str, ...] = ()
    search_depth: str = "basic"

@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str | None = None
    published_date: str | None = None
    score: float | None = None
```

在 `SearchOptions.__post_init__` 中校验枚举值和每类最多 20 个域名；`to_dict()` 保留三个原字段，并仅输出非空元数据。

- [ ] **步骤 4：运行模型测试确认通过**

运行：`python -m pytest tests/web_search/test_search.py -q`
预期：PASS。

### 任务 2：实现 Tavily 搜索源

**文件：**
- 修改：`iris_agent/web_search/sources.py`
- 测试：`tests/web_search/test_sources.py`

- [ ] **步骤 1：编写 Tavily 请求映射与错误测试**

```python
def test_tavily_source_maps_request_and_response():
    seen = {}
    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"results": [{
            "title": "结果", "url": "https://example.com/a",
            "content": "摘要", "score": 0.8, "published_date": "2026-08-22",
        }]})
    source = TavilySearchSource("secret", http_client=_json_client(handler))
    results = source.search("查询", 3, SearchOptions(topic="news", time_range="week"))
    assert seen["topic"] == "news"
    assert seen["time_range"] == "week"
    assert results[0].source == "tavily"

def test_tavily_source_hides_key_on_http_error():
    source = TavilySearchSource("secret", http_client=_error_client(401))
    assert source.search("查询", 5, SearchOptions()) == []
```

- [ ] **步骤 2：运行测试确认 Tavily 源尚不存在**

运行：`python -m pytest tests/web_search/test_sources.py -q`
预期：FAIL，无法导入 `TavilySearchSource`。

- [ ] **步骤 3：实现 Tavily 源和统一源签名**

```python
class TavilySearchSource:
    name = "tavily"

    def search(self, query: str, limit: int, options: SearchOptions | None = None) -> list[SearchResult]:
        opts = options or SearchOptions()
        payload = {
            "query": query, "max_results": limit,
            "topic": opts.topic, "search_depth": opts.search_depth,
        }
        # 有值时加入 time_range/include_domains/exclude_domains；
        # 使用 Authorization: Bearer <key> 请求头 POST /search，密钥不进入请求体。
```

响应只读取 `results` 数组，截断摘要并转换分数；所有网络、HTTP 和解码异常返回空列表。Bing 与 DuckDuckGo 通过查询操作符表达 `topic`、`include_domains` 和 `exclude_domains`；`search_depth` 仅 Tavily 使用，`time_range` 无法可靠表达时 fail-closed 并返回明确错误。

- [ ] **步骤 4：运行搜索源测试确认通过**

运行：`python -m pytest tests/web_search/test_sources.py -q`
预期：PASS。

### 任务 3：实现回退、重试与去重

**文件：**
- 修改：`iris_agent/web_search/search.py`
- 测试：`tests/web_search/test_search.py`

- [ ] **步骤 1：编写参数透传和规范 URL 去重测试**

```python
def test_search_passes_options_and_deduplicates_urls():
    first = RecordingSource([SearchResult("A", "https://EXAMPLE.com/a#x", "短", score=.8)])
    second = RecordingSource([SearchResult("A2", "https://example.com/a", "更完整摘要")])
    results = WebSearchClient(sources=[first, second]).search(
        "查询", limit=5, options=SearchOptions(topic="news")
    )
    assert len(results) == 1
    assert first.options.topic == "news"
```

- [ ] **步骤 2：运行聚合测试确认失败**

运行：`python -m pytest tests/web_search/test_search.py -q`
预期：FAIL，`search` 不接受 `options` 或结果未去重。

- [ ] **步骤 3：实现聚合逻辑**

将 `WebSearchClient.search` 扩展为 `search(query, limit=None, options=None)`；每个源最多尝试 `max_retries` 次。单个源返回结果后即结束回退；对该批结果规范 URL、合并重复项并按 `score` 稳定排序。错误文本只包含源名和状态，不包含请求头、请求体或密钥。

- [ ] **步骤 4：运行全部搜索模块测试**

运行：`python -m pytest tests/web_search -q`
预期：PASS。

### 任务 4：扩展 web_search 工具参数

**文件：**
- 修改：`iris_agent/tools/builtin/web_tools.py`
- 测试：`tests/tools/test_web_tools.py`

- [ ] **步骤 1：编写高级参数转发和非法参数测试**

```python
def test_web_search_tool_forwards_advanced_options():
    client = RecordingClient()
    result = build_web_search_tool(client).handler(
        query="最新模型", topic="news", time_range="week",
        include_domains=["openai.com"], search_depth="advanced",
    )
    assert client.options.include_domains == ("openai.com",)
    assert result[0]["source"] == "tavily"
```

- [ ] **步骤 2：运行工具测试确认失败**

运行：`python -m pytest tests/tools/test_web_tools.py -q`
预期：FAIL，处理器或 schema 不接受高级参数。

- [ ] **步骤 3：实现参数 schema 与转换**

工具 handler 构造 `SearchOptions`，将校验错误转换为 `ToolInvocationError("invalid_search_options", ...)`。JSON schema 为枚举字段声明允许值，域名数组设 `maxItems: 20`，并保留仅传 `query` 的旧调用方式。

- [ ] **步骤 4：运行工具测试确认通过**

运行：`python -m pytest tests/tools/test_web_tools.py -q`
预期：PASS。

### 任务 5：配置并装配 Tavily 首选源

**文件：**
- 修改：`iris_agent/config/settings.py`
- 修改：`iris_agent/bootstrap.py`
- 修改：`agent.yaml`
- 修改：`.env.example`
- 测试：`tests/config/test_settings.py`
- 测试：`tests/test_bootstrap_services.py`

- [ ] **步骤 1：编写环境变量和源顺序测试**

```python
def test_tavily_key_comes_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    assert load_settings(tmp_path / "missing.yaml").web_search.tavily_api_key == "test-tavily"

def test_bootstrap_places_tavily_before_bing(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    app = build_application(_config(tmp_path))
    assert app.settings.web_search.enable_tavily is True
    # 通过捕获 WebSearchClient 构造参数断言源名为 ["tavily", "bing"]。
```

- [ ] **步骤 2：运行配置与装配测试确认失败**

运行：`python -m pytest tests/config/test_settings.py tests/test_bootstrap_services.py -q`
预期：FAIL，配置字段或 Tavily 装配不存在。

- [ ] **步骤 3：增加安全配置**

`WebSearchSettings` 增加：

```python
enable_tavily: bool = True
tavily_api_key: str = ""
default_search_depth: str = "basic"
```

加载优先级为 `TAVILY_API_KEY` 环境变量，其次为空；不从 YAML 接受明文密钥。bootstrap 仅在开关开启且密钥非空时把 `TavilySearchSource` 放在 Bing 前。`agent.yaml` 只保存开关和默认深度，`.env.example` 添加 `TAVILY_API_KEY=`。

- [ ] **步骤 4：运行配置与装配测试确认通过**

运行：`python -m pytest tests/config/test_settings.py tests/test_bootstrap_services.py -q`
预期：PASS。

### 任务 6：创建深度联网研究 Skill

**文件：**
- 创建：`iris_agent/skill_center/bundled/web-research/SKILL.md`
- 测试：`tests/skill_center/test_catalog.py`

- [ ] **步骤 1：使用 skill-creator 技能检查项目 Skill 规范**

完整读取 skill-creator 指令，并对照现有 `hot-radar` 内置 Skill 的 frontmatter、发现规则与长度限制。

- [ ] **步骤 2：编写失败的技能发现测试**

```python
def test_catalog_discovers_web_research_skill(tmp_path):
    catalog = _bundled_catalog(tmp_path)
    skill = catalog.get("web-research")
    assert skill is not None
    assert "交叉验证" in skill.body
```

- [ ] **步骤 3：运行测试确认技能不存在**

运行：`python -m pytest tests/skill_center/test_catalog.py -q`
预期：FAIL，目录中没有 `web-research`。

- [ ] **步骤 4：编写精简的研究工作流**

Skill 必须明确：判断是否需要联网；简单问题单次搜索；复杂问题生成 2–4 个互补查询；时效问题设置 `time_range`；重要事实由两个独立来源支持；优先原始/官方来源；冲突不隐藏；最终答案为关键陈述附标题和 URL；禁止编造未返回的日期、作者或引文。

- [ ] **步骤 5：运行技能测试确认通过**

运行：`python -m pytest tests/skill_center/test_catalog.py -q`
预期：PASS。

### 任务 7：文档、回归与密钥审计

**文件：**
- 修改：`README.md`
- 修改：`docs/superpowers/specs/2026-08-22-tavily-web-search-enhancement-design.md`

- [ ] **步骤 1：补充配置和使用说明**

README 说明在 `.env` 设置 `TAVILY_API_KEY`、未设置时自动使用免费源，以及 `topic/time_range/include_domains/search_depth` 的用途；不得展示真实密钥。

- [ ] **步骤 2：运行定向测试**

运行：`python -m pytest tests/web_search tests/tools/test_web_tools.py tests/config/test_settings.py tests/test_bootstrap_services.py tests/skill_center/test_catalog.py -q`
预期：全部 PASS。

- [ ] **步骤 3：运行后端全量测试**

运行：`python -m pytest -q`
预期：全部 PASS，仅允许项目已有的 skip。

- [ ] **步骤 4：执行密钥与占位符审计**

扫描目标必须显式限定为 `iris_agent`、`tests`、`README.md`、`agent.yaml` 和 `.env.example`；不要以项目根目录 `.` 为目标，也绝不读取或输出用户的 `.env`。分别检查环境变量的非空赋值和疑似真实 Tavily 密钥形态：

```powershell
rg -n --hidden --glob '!**/.env' --glob '!**/.venv/**' --glob '!**/node_modules/**' --glob '!**/__pycache__/**' "TAVILY_API_KEY\s*=\s*\S+" iris_agent tests README.md agent.yaml .env.example
rg -n --hidden --glob '!**/.env' --glob '!**/.venv/**' --glob '!**/node_modules/**' --glob '!**/__pycache__/**' "tvly-[A-Za-z0-9_-]{20,}" iris_agent tests README.md agent.yaml .env.example
```

预期：两次扫描均无匹配；源码、配置、README 和测试中没有疑似真实密钥，`.env.example` 仅保留 `TAVILY_API_KEY=` 空值占位符。测试中的普通占位字符串不按真实密钥误报。

- [ ] **步骤 5：记录验证结果**

在本计划末尾追加执行日期、定向测试数量、全量测试数量、skip 数量及密钥审计结论。

## 计划自检

- 规格覆盖：任务 1 覆盖统一模型，任务 2 覆盖 Tavily，任务 3 覆盖回退与去重，任务 4 覆盖工具接口，任务 5 覆盖安全配置，任务 6 覆盖研究 Skill，任务 7 覆盖文档与全量验证。
- 占位符扫描：每个代码变更均给出具体签名、字段、测试或行为，没有未落实的实现项。
- 类型一致性：所有源使用 `SearchOptions`；客户端和工具均以同一类型透传；`SearchResult` 元数据命名在模型、Tavily 映射和工具输出中一致。
- 工作区说明：当前目录不是 Git 仓库，因此不安排 commit 步骤；若执行时已初始化 Git，则按任务粒度提交。

## 执行结果（2026-08-22）

- README 已补充 Tavily 环境变量、免费源回退、搜索配置、高级参数、输入边界、流式下载上限和 `web-research` Skill 的简要说明；未写入真实密钥。
- 定向测试：`.\.venv\Scripts\python.exe -m pytest tests/web_search tests/tools/test_web_tools.py tests/config/test_settings.py tests/test_bootstrap_services.py tests/skill_center/test_catalog.py -q`，结果为 `315 passed`、0 失败（7 条弃用警告）。
- 后端全量测试：`.\.venv\Scripts\python.exe -m pytest -q`，结果为 `937 passed, 4 skipped`、0 失败（23 条弃用警告）。
- 语法检查：`.\.venv\Scripts\python.exe -m compileall -q iris_agent tests iris_agent.py server.py`，退出码 0。
- 密钥审计：使用目标白名单，仅扫描 `iris_agent`、`tests`、`README.md`、`agent.yaml` 和 `.env.example`，同时通过 glob 显式排除 `.env`、`.venv`、`node_modules`、`__pycache__`，并排除本计划中的示例测试字符串。`TAVILY_API_KEY` 非空赋值模式和疑似真实 Tavily 密钥形态均无匹配；`.env.example` 保持空值占位符。
