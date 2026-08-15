# 设计规格：联网搜索（一期）

日期：2026-08-15
分支：feature/web-search（计划）
参考：hermes `agent/browser_provider.py`（取轻量替代）、iris `aihot_daily/client.py`（现有抓取模式）

## 1. 背景与目标

iris 目前只能抓固定资讯源（AI HOT 日报、热点雷达），**没有按任意问题联网搜索的能力**——用户问「查一下 Agent 开发面试经验」，iris 只能回复「无法联网」。

目标：给 iris 加两个只读工具，让它能**搜索 + 抓取网页 + 总结**：

- `web_search(query, limit)`：搜索关键词，返回结果列表（标题 + 摘要 + URL）。
- `fetch_page(url)`：抓取指定网页，提取正文纯文本。

用户选择：**免费接口 + 中文为主**。搜索源用 **Bing 网页版**（无需 API key），配合 httpx + HTML 解析。

## 2. 数据模型

新模块 `iris_agent/web_search/`：

```python
@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self): ...
```

## 3. 核心流程

```
Agent 调用 web_search(query, limit)
  → WebSearchClient.search(query, limit)
      → httpx GET Bing 搜索页（中文 User-Agent）
      → 解析 <li class="b_algo"> 结构，提取标题/URL/摘要
      → 返回前 limit 条 SearchResult（摘要截断）

Agent 调用 fetch_page(url)
  → PageFetcher.fetch(url)
      → 校验 URL（http/https + 内网 IP 黑名单，防 SSRF）
      → httpx GET 网页
      → bs4 提取正文：去 script/style/nav/header/footer，取 <p> 等文本
      → 返回截断后的纯文本
```

## 4. 配置

`agent.yaml` 新增 `web_search:` 节 → `WebSearchSettings`：

| 键 | 默认 | 说明 |
|----|------|------|
| `enabled` | true | 是否启用 |
| `timeout_seconds` | 15 | 请求超时 |
| `max_results` | 5 | 搜索返回条数上限 |
| `max_snippet_chars` | 300 | 摘要截断 |
| `max_page_chars` | 8000 | 正文截断 |

## 5. 安全边界

- 两个工具均 `requires_approval=False`（只读）。
- `fetch_page` 只允许 `http/https`，**拒绝内网/回环地址**（`localhost`、`127.x`、`10.x`、`172.16-31.x`、`192.168.x`、`169.254.x`），防 SSRF。
- 搜索与抓取均设超时；失败返回错误信息，不抛异常给主循环。
- 正文/摘要截断，避免超长内容撑爆上下文。

## 6. 一期不做

- 真浏览器（Playwright/JS 渲染）——留后续。
- 搜索源切换 UI（Bing 硬编码，可后续加 DuckDuckGo/SerpAPI）。
- 网页缓存 / 结果持久化。

## 7. 验收标准

- [ ] `web_search` 返回中文搜索结果（标题/URL/摘要）。
- [ ] `fetch_page` 抓取网页并提取正文纯文本。
- [ ] SSRF 防护：内网/回环地址被拒绝。
- [ ] 超时与失败不抛异常给主循环。
- [ ] 后端全量测试通过。
