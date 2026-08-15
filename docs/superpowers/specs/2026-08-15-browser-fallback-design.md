# 设计规格：真浏览器兜底（一期）

日期：2026-08-15
分支：feature/browser-fallback（计划）

## 1. 背景与目标

当前 `fetch_page` 用 httpx 抓取 HTML，遇到两类问题无能为力：

1. **JS 动态页面**：React/Vue 前端返回空壳 HTML，正文由 JS 渲染，httpx 抓出来没有内容。
2. **强反爬**：Cloudflare 人机验证等，httpx 无法通过。

目标：给 `fetch_page` 加一个**真浏览器兜底**——httpx 抓不到（失败或内容为空壳）时，自动降级到 Playwright 驱动**系统浏览器**（Chrome/Edge）抓取，覆盖 httpx 无能为力的场景。

## 2. 关键设计

**零内核下载**：系统已装 Chrome 和 Edge，Playwright 用 `channel="chrome"` 驱动系统浏览器，**不需要 `playwright install` 下载内核**。

### 降级触发条件（满足其一即降级）

- httpx 抓取失败（重试耗尽后抛错）。
- httpx 抓取成功但正文 < `min_text_chars`（默认 200，判定为 JS 空壳）。

### 数据流

```
fetch_page(url)
  → httpx 抓取（含反爬重试）
      → 成功且正文 ≥ 阈值 → 返回
      → 失败或正文过少 → 降级 BrowserFetcher（若启用）
          → 成功 → 返回
          → 失败 → 抛错
```

### BrowserFetcher

新模块 `web_search/browser_fetcher.py`，用 Playwright **同步 API**：

```python
class BrowserFetcher:
    def __init__(self, channel="chrome", timeout=30, max_page_chars=30000, enabled=True):
        ...
    def fetch(self, url) -> str:
        # 复用 PageFetcher 的 SSRF 校验
        with sync_playwright() as p:
            browser = p.chromium.launch(channel=self.channel, headless=True)
            page = browser.new_page()
            page.goto(url, timeout=...)
            page.wait_for_load_state("networkidle")  # 等 JS 渲染
            return page.inner_text("body")[: max_page_chars]
```

## 3. 配置

`agent.yaml` 的 `web_search:` 节新增：

| 键 | 默认 | 说明 |
|----|------|------|
| `enable_browser_fallback` | false | 是否启用真浏览器兜底 |
| `browser_channel` | msedge | 系统浏览器通道（msedge 已验证可用；chrome 亦可配置） |
| `min_text_chars` | 200 | 判定 JS 空壳的正文阈值 |

默认 `false`（因为重、慢、依赖系统浏览器），用户按需开启。

## 4. 安全与边界

- BrowserFetcher 复用 `PageFetcher._validate_url` 的 SSRF 校验。
- 浏览器 headless 模式，超时兜底。
- 正文截断 `max_page_chars`。

## 5. 一期不做

- 浏览器交互（点击/登录/翻页）。
- 截图、PDF 导出。
- 浏览器复用池（每次启动新浏览器，简单但慢）。

## 6. 验收标准

- [ ] httpx 抓取失败时，若启用兜底，自动用浏览器抓取成功。
- [ ] httpx 抓到 JS 空壳时，降级浏览器拿到渲染后正文。
- [ ] 复用 SSRF 校验。
- [ ] 默认关闭，不影响现有行为。
- [ ] 后端全量测试通过。
