# 实现计划：联网搜索（一期）

日期：2026-08-15
分支：feature/web-search

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | 搜索模型 + Bing 搜索客户端 | `web_search/models.py` + `web_search/search.py` |
| 2 | 网页抓取器 | `web_search/fetcher.py`（httpx + bs4 + SSRF 防护） |
| 3 | web_search + fetch_page 工具 | `tools/builtin/web_tools.py` |
| 4 | 配置 + 装配 | `settings.py` + `bootstrap.py` + `agent.yaml` |
| 5 | 全量验证 | 后端 pytest + 依赖安装 + 文档 |

## 任务细节

### 任务 1：搜索模型 + Bing 搜索客户端
- `SearchResult` 数据类；`WebSearchClient.search(query, limit)`：httpx GET Bing 搜索页 + bs4 解析 `<li class="b_algo">`，返回结果（摘要截断）。
- 依赖：`beautifulsoup4`（加入 requirements，用清华镜像安装）。
- 测试：`tests/web_search/test_search.py`（monkeypatch httpx 返回固定 HTML）。

### 任务 2：网页抓取器
- `PageFetcher.fetch(url)`：URL 校验（http/https + 内网 IP 黑名单）→ httpx GET → bs4 提取正文 → 截断。
- 测试：`tests/web_search/test_fetcher.py`（SSRF 拒绝、正文提取、截断）。

### 任务 3：web_search + fetch_page 工具
- `build_web_search_tool` / `build_fetch_page_tool`，`requires_approval=False`，导出。
- 测试：`tests/tools/test_web_tools.py`。

### 任务 4：配置 + 装配
- `WebSearchSettings`；`bootstrap.py` 构造 client/fetcher 并注册工具；`agent.yaml` 加 `web_search:` 节。
- 测试：装配测试。

### 任务 5：全量验证
- 后端全量 pytest + 隐私核对；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖搜索；任务 2 覆盖抓取；任务 3 覆盖工具；任务 4 覆盖配置装配；任务 5 覆盖验证。
- 类型一致性：`SearchResult.to_dict` 与工具返回一致；工具复用 client/fetcher。
- 安全边界：只读工具；SSRF 黑名单；超时；截断；失败返回错误不抛异常。

## 执行结果（2026-08-15）

- 5 个任务全部完成并提交（4 个 commit）：搜索客户端 → 抓取器 → 工具 → 配置/装配 → 文档。
- 核心实现：`web_search/models.py`（SearchResult）、`search.py`（Bing 网页版 HTML 解析，httpx+bs4）、`fetcher.py`（SSRF 防护 + 正文提取）、`tools/builtin/web_tools.py`（web_search/fetch_page，requires_approval=False）、`WebSearchSettings`。
- 依赖：新增 `beautifulsoup4>=4.12,<5`（清华镜像装）。
- 全量验证：后端 `462 passed, 3 skipped, 0 failed`（新增 27 条搜索测试全绿）。
- 隐私核对：只读工具；SSRF 拒绝内网/回环；摘要/正文截断。

