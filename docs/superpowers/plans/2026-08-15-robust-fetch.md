# 实现计划：抓取健壮性 + 错误自愈（一期）

日期：2026-08-15
分支：feature/robust-fetch

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | fetch_page 反爬重试 | `web_search/fetcher.py`（换头重试） |
| 2 | 搜索源可插拔 + DuckDuckGo 源 | `web_search/sources.py`（Bing/DuckDuckGo） |
| 3 | web_search 多源降级 + 重试 | `web_search/search.py` |
| 4 | 配置 + 装配 + system prompt 自愈指引 | `settings.py` + `bootstrap.py` + `agent.yaml` |
| 5 | 全量验证 | 后端 pytest + 文档 |

## 任务细节

### 任务 1：fetch_page 反爬重试
- `PageFetcher.fetch`：遇 521/403/429 换 UA（移动端）+ Referer 重试，最多 `max_retries` 次。
- 测试：`tests/web_search/test_fetcher.py` 加反爬重试用例（MockTransport 先返回 521 再返回 200）。

### 任务 2：搜索源可插拔
- 新建 `web_search/sources.py`：`BingSearchSource`（迁移现有 Bing 逻辑）、`DuckDuckGoSearchSource`。
- 测试：`tests/web_search/test_sources.py`。

### 任务 3：web_search 多源降级 + 重试
- `WebSearchClient` 改为持有 `sources` 列表，依次降级；网络失败重试 1 次。
- 测试：`tests/web_search/test_search.py` 更新 + 降级用例。

### 任务 4：配置 + 装配 + 自愈指引
- `WebSearchSettings` 加 `max_retries`/`enable_duckduckgo`；`bootstrap.py` 按配置构造 sources；`agent.yaml` 加配置 + system prompt 自愈指引。
- 测试：装配测试。

### 任务 5：全量验证
- 后端全量 pytest + 隐私核对；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖反爬重试；任务 2/3 覆盖多源降级；任务 4 覆盖配置与自愈指引；任务 5 覆盖验证。
- 类型一致性：`SearchSource` 统一 `search(query, limit) -> list[SearchResult]`。
- 安全边界：重试仍走 SSRF 校验；备用源默认关闭；失败信息透出。

## 执行结果（2026-08-15）

- 5 个任务全部完成并提交（4 个 commit）：反爬重试 → 搜索源可插拔 → 多源降级 → 配置/装配/自愈指引 → 文档。
- 核心实现：`fetcher.py` 遇 521/403/429 换移动端 UA 重试（max_retries=2）；`sources.py`（BingSearchSource + DuckDuckGoSearchSource）；`search.py` 多源依次降级 + 每源重试 1 次；`WebSearchSettings` 加 max_retries/enable_duckduckgo；system prompt 加工具失败自愈指引。
- 关键结论：国内免费无 key 搜索备用源不可得（DuckDuckGo 被墙、搜狗/360 反爬），故 DuckDuckGo 仅作可选源默认关闭。
- 全量验证：后端 `474 passed, 3 skipped, 0 failed`（新增 12 条测试全绿）。

