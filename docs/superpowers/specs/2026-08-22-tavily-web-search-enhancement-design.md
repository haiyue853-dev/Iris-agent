# Tavily 联网搜索增强设计

日期：2026-08-22

## 目标

在保留现有 Bing 与 DuckDuckGo 搜索能力的基础上，将 Tavily 作为配置了密钥时的首选搜索源，提高中文问答的结果质量、时效筛选能力与来源可追溯性；同时增加一个研究型 Skill，指导 Agent 对复杂问题执行多轮检索和交叉验证。

## 架构

搜索链按 `Tavily → Bing → DuckDuckGo` 顺序运行。Tavily 仅在 `TAVILY_API_KEY` 存在时装配；没有密钥、请求失败、超时或无结果时，不影响现有免费搜索源。`WebSearchClient` 负责回退、URL 规范化、跨源去重和结果数量限制，搜索源只负责调用各自服务并转换统一模型。

## 数据模型与接口

`SearchResult` 保留 `title`、`url`、`snippet`，新增可选的 `source`、`published_date` 和 `score`。现有调用方继续可用；`to_dict()` 只新增有值的元数据，便于 Agent 在回答中展示来源、日期并判断可信度。

`web_search` 工具继续接受 `query` 和 `limit`，新增可选参数：

- `topic`: `general` 或 `news`。
- `time_range`: `day`、`week`、`month`、`year`。
- `include_domains` / `exclude_domains`: 域名白名单与黑名单。
- `search_depth`: `basic` 或 `advanced`，仅 Tavily 使用。

Tavily 原生使用全部高级参数。Bing 与 DuckDuckGo 免费回退源通过查询操作符保留 `topic`、`include_domains` 和 `exclude_domains` 语义；`search_depth` 为 Tavily 专属，不改变免费源行为。免费源无法可靠表达 `time_range`，因此请求包含时间范围而 Tavily 不可用或失败时采用 fail-closed：停止回退并返回明确的“不支持该筛选条件”错误，不静默放宽为无时间限制的搜索。

## 配置与密钥

`WebSearchSettings` 新增 Tavily 开关、搜索深度、域名数量限制和 `max_download_bytes`。下载上限默认 2,000,000 字节，可配置范围为 1 到 20,000,000 字节；`fetch_page` 以流式方式读取响应，在 `Content-Length` 已超限或累计字节数越界时立即终止。

密钥只从 `TAVILY_API_KEY` 环境变量读取，不写入 `agent.yaml`，不出现在日志、工具结果或错误消息中。`.env.example` 仅加入空白示例项。Tavily 请求使用官方 `Authorization: Bearer ...` 认证头，密钥不放入 JSON 请求体。

## 质量策略

- 对 URL 去除 fragment，并规范 host、默认端口和尾部斜杠后去重。
- 同一 URL 多次出现时保留信息更完整、相关度更高的结果。
- Tavily 返回顺序与相关度分数作为主排序依据；回退源保持其原始顺序。
- 不在底层搜索客户端调用 LLM 做查询改写，避免一次普通搜索产生不可控费用和延迟。
- 复杂问题的拆词、多轮搜索、来源交叉验证由研究 Skill 指导 Agent 完成。

## 研究 Skill

新增内置 `web-research` Skill：简单事实进行一次精准搜索；复杂或时效性问题生成 2–4 个互补查询；重要结论至少比较两个独立来源；存在冲突时明确陈述差异；最终回答附可点击来源，不伪造发布日期或引用。

## 故障与安全

- Tavily 的 401/403、429、5xx、超时与数据格式错误统一转为空结果并记录不含密钥的源级错误，随后回退。
- 查询最长 500 字符；`limit` 范围为 1 到 20。每类域名列表最多 20 项，每项必须是最长 253 字符的纯域名（不接受 URL 或 IP 地址）。
- `max_download_bytes` 默认 2 MB、允许范围 1 字节到 20 MB；网页正文按流读取并在超限时终止，避免先完整缓冲不受信任响应。
- 继续沿用 `fetch_page` 的 SSRF 防护；搜索结果不自动抓取任意内网页面。
- 不缓存密钥或完整第三方响应。

## 验收标准

- 配置 `TAVILY_API_KEY` 后 Tavily 为首选源；未配置时现有搜索正常工作。
- Tavily 参数与响应映射正确，错误时自动回退。
- 重复 URL 被合并，结果包含可用的来源和发布日期元数据。
- `web_search` 工具向后兼容并支持高级筛选参数。
- `web-research` Skill 可被技能中心发现并包含多轮检索与引用规范。
- 搜索相关测试、后端全量测试通过，密钥不进入仓库或输出。

## 非目标

- 本轮不接入 Brave 或第二个付费搜索 API。
- 本轮不做搜索结果持久缓存、搜索历史 UI 或独立研究报告页面。
- 本轮不强制每个聊天请求联网；是否调用搜索仍由 Agent 与联网模式共同决定。
