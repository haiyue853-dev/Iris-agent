# 设计规格：抓取健壮性 + 错误自愈（一期）

日期：2026-08-15
分支：feature/robust-fetch（计划）

## 1. 背景与目标

用户实际遇到的痛点：CSDN 抓取返回 521（反爬）、搜索偶发失败。当前 `fetch_page` 遇到反爬直接失败、`web_search` 失败即返回空，用户要手动重试。

目标：让抓取和搜索**遇到反爬/偶发失败时自动重试**，并在 Agent 层加「工具失败后换策略」的自愈指引，让「查资料」更可靠、无感。

## 2. 范围

1. **fetch_page 反爬重试**（核心）：遇 521/403/429 等反爬状态码，自动换请求头重试（最多 2 次）。
2. **web_search 失败重试**：网络错误自动重试 1 次。
3. **搜索源可插拔架构**：把 Bing 抽成独立 source，新增 DuckDuckGo source（默认关闭，配置可启用）；`WebSearchClient` 支持多 source 依次降级。
4. **Agent 错误自愈指引**：system prompt 加「工具失败后读错误、换策略重试、不轻易放弃」规则。

## 3. 关键设计

### fetch_page 反爬重试

```
fetch(url)
  → 尝试 1：完整浏览器请求头
      → 200 成功 → 提取正文
      → 521/403/429 → 换 UA（移动端）+ 加 Referer，尝试 2
      → 仍失败 → 尝试 3（最后一次）
  → 全失败 → 抛 ValueError（含各次状态码）
```

### 搜索源可插拔

```python
class SearchSource(Protocol):
    name: str
    def search(self, query: str, limit: int) -> list[SearchResult]: ...

class BingSearchSource: ...        # 现有 Bing 逻辑
class DuckDuckGoSearchSource: ...  # 备用（默认不启用，国内被墙）

class WebSearchClient:
    def __init__(self, ..., sources=None):
        self.sources = sources or [BingSearchSource(...)]
    def search(self, query, limit):
        for source in self.sources:   # 依次降级
            results = source.search(query, limit)
            if results: return results
        return []
```

### Agent 错误自愈指引

system prompt 追加：工具调用失败时，读错误信息，换关键词/换 URL/换工具重试，不要直接放弃。

## 4. 配置

`agent.yaml` 的 `web_search:` 节新增：

| 键 | 默认 | 说明 |
|----|------|------|
| `max_retries` | 2 | fetch_page 反爬重试次数 |
| `enable_duckduckgo` | false | 是否启用 DuckDuckGo 备用源 |

## 5. 一期不做

- 真正的备用搜索源（国内免费无 key 源不可得，DuckDuckGo 仅作可选）。
- 代理支持。
- 抓取结果缓存。

## 6. 验收标准

- [ ] fetch_page 遇 521/403/429 自动重试，最终成功或给出各次状态码。
- [ ] web_search 网络失败自动重试 1 次。
- [ ] 多源降级架构可用（Bing 失败且启用 DuckDuckGo 时降级）。
- [ ] system prompt 含错误自愈指引。
- [ ] 后端全量测试通过。
