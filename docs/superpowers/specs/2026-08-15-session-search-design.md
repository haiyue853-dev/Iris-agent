# 会话搜索召回一期设计（P2）

日期：2026-08-15  
状态：方案待确认

## 目标与范围

让 Iris 能检索并引用历史会话——当用户说「上次我们聊的 XX 进展如何」时，Agent 能搜索过往会话，找到相关内容并回答。

一期只做「会话搜索服务 + 主动召回工具 + 搜索 API」，不做 LLM 摘要、不做自动注入、不做前端搜索 UI。搜索由 Agent 通过内置 `recall` 工具**主动触发**，符合 hermes「Agent 决定何时回忆」的模式，避免每条消息都注入历史上下文、保护 prompt 缓存。

## 方案选择

- **搜索算法**：字符 bigram（中文）+ 小写 word（英文）混合分词，计算 query 与文档 token 的重叠度。无外部依赖，对中文有效，不引入 SQLite/FTS5（iris 当前会话是 JSON 文件存储，保持不动）。
- **索引策略**：一期每次搜索时扫描会话 JSON（`JsonSessionRepository.list()` 已加载全部会话）。个人助手会话量级下足够快；会话量大时再引入持久化索引（后续）。

## 数据模型

`SearchHit`（`iris_agent/session_search/models.py`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | `str` | 来源会话 |
| `session_name` | `str` | 会话名 |
| `role` | `str` | `user` / `assistant` |
| `content` | `str` | 匹配到的消息片段（截断至 300 字符） |
| `updated_at` | `float` | 会话更新时间（用于排序） |
| `score` | `int` | 相关度（匹配 token 数） |

## 搜索算法

`tokenize(text)`：中文按连续二字切分（bigram），英文按小写单词切分，返回 token 集合。例如「聊聊项目 Python」→ `{聊聊, 聊项, 项目, python}`。

`search(query, limit)`：对每个会话的每条 user/assistant 消息计算 `score = len(query_tokens ∩ message_tokens)`，`score > 0` 的片段按 `score` 降序、`updated_at` 降序取前 `limit` 条（默认 5）。

## 服务

`SessionSearchService`（`iris_agent/session_search/service.py`）：

- `search(query, limit=5) -> list[SearchHit]`

服务持有 `SessionRepository` 引用，每次搜索调用 `sessions.list()` 扫描。只读取 `role in {user, assistant}` 且非空 `content` 的消息；不触碰 `tool` 消息、工具参数、工具结果、环境变量或密钥。

## 召回工具

`iris_agent/tools/builtin/recall_tool.py`：

```python
def build_recall_tool(search: SessionSearchService) -> Tool:
    def recall(query: str):
        hits = search.search(query)
        return {"hits": [hit.to_dict() for hit in hits]}
    return Tool("recall", "搜索历史会话，召回与查询相关的内容", {...}, recall, requires_approval=False)
```

`requires_approval=False`：只读检索，安全。工具返回结构化的命中片段，由 Agent 自行综合回答，不额外调用 LLM 摘要。

## HTTP API

新增 `iris_agent/api/search_api.py`：

| 接口 | 作用 |
| --- | --- |
| `GET /api/search?query=...&limit=5` | 返回相关历史片段（白名单字段） |

`limit` 上限 20，`query` 非空。响应不含工具参数、结果、密钥或原始异常。

## 配置与装配

`SessionSearchSettings`（`config/settings.py`）：`max_hit_chars=300`、`default_limit=5`。`bootstrap.py` 构造 `SessionSearchService(sessions)`、注册 `build_recall_tool(search)`、装配到 `ApplicationServices` 与 `create_app`。

## 隐私与安全

- 仅搜索并返回 user/assistant 的文本内容，`tool` 角色消息一律跳过。
- 命中片段截断到固定长度，不返回完整会话或任何敏感 payload。
- `recall` 工具为只读，不写入、不修改任何会话。

## 测试与验收

后端覆盖：

- `tokenize` 对中文 bigram、英文 word、混合文本的分词正确性；
- `search` 返回按相关度排序的命中片段，`score=0` 的会话不出现，`limit` 生效；
- 空 query 返回空，`tool` 消息与空内容被跳过；
- `recall` 工具返回结构化命中、非法参数错误码；
- 装配与 `GET /api/search` 的校验、字段白名单。

验收标准：用户问「上次聊的 XX」时，Agent 能通过 `recall` 工具检索到相关历史片段并回答；搜索过程不泄露工具参数、结果、密钥；不命中时返回空结果、不报错。
