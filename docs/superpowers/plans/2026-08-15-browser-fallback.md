# 实现计划：真浏览器兜底（一期）

日期：2026-08-15
分支：feature/browser-fallback

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | BrowserFetcher 浏览器抓取器 | `web_search/browser_fetcher.py`（Playwright 同步 API + SSRF 复用） |
| 2 | PageFetcher 降级集成 | `web_search/fetcher.py`（失败/空壳降级） |
| 3 | 配置 + 装配 | `settings.py` + `bootstrap.py` + `agent.yaml` |
| 4 | 全量验证 | 后端 pytest + 真实浏览器验证 + 文档 |

## 任务细节

### 任务 1：BrowserFetcher
- `web_search/browser_fetcher.py`：`BrowserFetcher.fetch(url)`，Playwright sync API 驱动系统浏览器（channel=chrome/msedge），复用 `PageFetcher._validate_url`。
- 测试：`tests/web_search/test_browser_fetcher.py`（monkeypatch playwright，验证 URL 校验 + 文本提取 + 截断）。

### 任务 2：PageFetcher 降级集成
- `PageFetcher` 加可选 `browser_fetcher` + `min_text_chars`；`fetch` 失败或正文过少时降级。
- 测试：`tests/web_search/test_fetcher.py` 加降级用例（httpx 空壳 → 浏览器成功）。

### 任务 3：配置 + 装配
- `WebSearchSettings` 加 `enable_browser_fallback`/`browser_channel`/`min_text_chars`；`bootstrap.py` 按配置构造 BrowserFetcher 注入 PageFetcher；`agent.yaml` 加配置。
- 测试：装配测试。

### 任务 4：全量验证
- 后端全量 pytest；真实浏览器实测（驱动 Chrome 抓一个 JS 页面）；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖浏览器抓取；任务 2 覆盖降级；任务 3 覆盖配置装配；任务 4 覆盖验证。
- 类型一致性：`BrowserFetcher.fetch(url) -> str` 与 `PageFetcher.fetch` 一致。
- 安全边界：复用 SSRF 校验；headless；超时；默认关闭。

## 执行结果（2026-08-15）

- 4 个任务全部完成并提交（3 个 commit）：BrowserFetcher → 降级集成 → 配置/装配 → 文档。
- 核心实现：`browser_fetcher.py`（Playwright sync API，channel 默认 msedge，复用 PageFetcher SSRF 校验）；`fetcher.py` 加 browser_fetcher/min_text_chars，httpx 失败或正文过少时降级；`WebSearchSettings` 加 enable_browser_fallback/browser_channel/min_text_chars。
- 关键结论：系统 Chrome 驱动失败（channel=chrome），**Edge（msedge）验证可用**；用 `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` 装包、免下载内核。playwright 1.62.0 已装。
- 全量验证：后端 `481 passed, 3 skipped, 0 failed`；真实浏览器抓 example.com 成功（129 字）。

