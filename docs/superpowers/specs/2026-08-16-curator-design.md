# Curator 后台审查一期设计规格

日期：2026-08-16
状态：方案草拟（待确认）

## 1. 背景与目标

iris-agent 已具备「学习闭环」：`remember`（记忆）、`save_skill`（技能）、`add_knowledge`（知识库）、画像自动提取都会让 agent **只增不减**地积累数据。时间一长必然出现重复、矛盾、过期、碎片化，污染注入上下文、浪费 token、甚至让 agent 按过期信息回答。

Curator 是一个**后台审查进程**，周期性（或手动）审视已积累的数据资产，产出「建议」供用户确认后应用。核心原则：

- **审查与执行分离**：curator 只产出审查报告（建议），**不自动删改数据**；用户在前端确认后，才真正合并/删除。避免误删。
- **只读运行**：审查阶段不修改任何记忆/画像/技能/知识，仅读取。
- **数据不出本机**：去重用本地 Ollama embedding（复用刚启用的 `bge-m3`），冲突精判用已配置的 LLM provider。

## 2. 范围

### 一期做（记忆 + 用户画像）

| 审查对象 | 数据来源 | 审查动作 |
|---------|---------|---------|
| 记忆 `MemoryEntry` | `MemoryService` | 去重（`merge`）、冲突（`conflict`） |
| 用户画像 `UserProfile`（`preferences`/`goals`/`facts` 列表） | `ProfileService` | 列表内去重（`dedupe`）、列表内冲突（`conflict`） |

一期只处理「同 category 的记忆对」和「画像同一列表字段内的条目对」，不跨类别、不跨字段。

### 一期不做（留二期）

- **技能库**去重/冲突（`SkillDefinition` 有 bundled/user 边界，规则更复杂，且 P3 刚落地数据量小）。
- **知识库**去重/冲突（面经条目，与记忆结构差异大）。
- **清过期**（`expire`）：过期判定需要「时效性 + 使用频率」等主观信号，一期不引入。
- **归纳整合**（`consolidate`）：碎片 → 精炼长期记忆，需要 LLM 生成合并文本，复杂度高，留二期。
- **自动应用**：一期全部走「人工确认后应用」，不做「无人值守自动删改」。
- **向量持久化**：审查按需临时 embed，不持久化向量（同知识库二期策略）。

## 3. 审查机制

### 3.1 候选生成

对审查对象按规则生成候选对，控制规模：

- **记忆**：对同一 `category` 的记忆，两两组成候选对。
- **画像**：对同一列表字段（`preferences`/`goals`/`facts`）内的条目，两两组成候选对。
- 候选对总数受 `max_pairs_per_run`（默认 200）上限约束，超出时按 `updated_at` 倒序截断，保证审查耗时可控。

### 3.2 相似度打分（确定性，无 LLM）

复用 `OllamaEmbedder`（`iris_agent/knowledge/embedder.py`，模型 `bge-m3`）对候选对两侧文本做向量化，算余弦相似度。

- `sim > merge_threshold`（默认 0.85）→ 判为**重复**，生成 `merge` 建议，无需 LLM。
- `sim ≤ conflict_threshold`（默认 0.45）→ 视为无关，丢弃。
- `conflict_threshold < sim ≤ merge_threshold` → 进入 LLM 精判（第 3.3 节）。

**降级**：Ollama 不可用 / 未拉 `bge-m3` / 未开 embeddings 时，退化为「字符 bigram 重叠度」（复用 `session_search.tokenizer.tokenize`），重叠度 > 阈值判为重复候选。保证 curator 始终可用（同知识库检索的降级思路）。降级模式下不进入 LLM 冲突精判（缺少相似度信号），只做确定性去重。

### 3.3 冲突精判（LLM，可开关）

对落在 `(conflict_threshold, merge_threshold]` 区间的候选对，调用已配置的 LLM provider 精判：

- 输入：两条条目的 `content`（或画像条目文本）——**只发送条目文本，绝不发送工具参数、密钥、环境变量**。
- 输出：`duplicate`（其实重复）/ `conflict`（语义相斥）/ `unrelated`（无关）。
- `duplicate` → 生成 `merge` 建议；`conflict` → 生成 `conflict` 建议；`unrelated` → 丢弃。
- 受 `enable_llm`（默认 `true`）开关控制；关闭时跳过此步，只做第 3.2 节的确定性去重。

### 3.4 建议生成

每条建议包含足够信息让用户判断，不展开敏感内容：

- `kind`：`merge` / `conflict` / `dedupe`。
- `scope`：`memory` / `profile`。
- `targets`：涉及的条目 id 列表（记忆 `memory_xxx`，画像字段用 `profile:<field>:<index>`）。
- `keep` / `drop`：应用时保留哪条、删除哪条（`merge` 与 `conflict` 均保留 `updated_at` 较新的那条；`dedupe` 保留列表首项）。
- `summary`：一句话说明（如「两条记忆语义重复：『用户偏好 React』 与 『用户偏好 React 框架』」）。
- `reason`：来源（`embedding` / `llm`）。

## 4. 触发机制

- **手动触发（一期核心）**：`POST /api/curator/run`，同步执行一次审查并返回报告；前端提供「立即审查」按钮。
- **定时触发（可选）**：复用 `AutomationScheduler` 的 cron 能力，允许用户在前端建一个周期任务，到点调用审查（仅生成报告，不自动应用）。一期先实现手动触发 + API 层面的定时钩子，前端定时 UI 可在确认手动流程后补。
- 审查为同步执行：当前记忆/画像量级（几十~几百条）下 embedding + 可选 LLM 精判在秒级完成；`max_pairs_per_run` 保证上限。

## 5. 数据模型与存储

### 5.1 模型（`iris_agent/curator/models.py`）

```text
CuratorReport
  id, scope ("memory"|"profile"), status ("open"|"applied"|"dismissed")
  created_at, summary, suggestions: CuratorSuggestion[]

CuratorSuggestion
  id, kind ("merge"|"conflict"|"dedupe"), scope ("memory"|"profile")
  targets: str[], keep: str, drop: str
  summary, reason ("embedding"|"llm"), applied: bool
```

字段均为白名单，`targets`/`keep`/`drop` 只存条目 id（或 `profile:<field>:<index>`），不存条目正文；正文由前端按 id 从各自 API 现取，避免报告里重复存储敏感/过期文本。

### 5.2 存储（`iris_agent/curator/repository.py`）

- 每条报告一个 JSON 文件：`data/curator/reports/<report_id>.json`（复用知识库「每条目一文件 + 原子写 + Windows 文件锁」模式）。
- `CuratorRepository`：`save(report)` / `get(id)` / `list()` / `update(report)`。
- 保留最近 N 份报告（`max_reports`，默认 50），写入前裁剪最旧。

## 6. 服务与装配

`CuratorService`（`iris_agent/curator/service.py`）：

- `run() -> CuratorReport`：只读遍历记忆/画像，生成候选对 → 相似度打分 →（可选）LLM 精判 → 生成报告并落盘。**不修改数据**。
- `apply(report_id, suggestion_ids=None) -> int`：对指定建议（缺省为全部）执行动作——通过 `MemoryService.delete()` / `ProfileService.replace()` 完成，**复用现有服务以保持锁与一致性**；更新建议 `applied` 与报告 `status`。
- `dismiss(report_id, suggestion_ids=None)`：忽略建议，更新状态。

`bootstrap.py` 注入 `CuratorService`（依赖 `MemoryService`、`ProfileService`、`OllamaEmbedder`、LLM provider），注册到 `ApplicationServices`。不注册进 `ToolRegistry`（curator 是后台系统能力，不是 Agent 可调工具）。

## 7. API（`iris_agent/api/curator_api.py`）

| 接口 | 方法 | 作用 |
|------|------|------|
| `/api/curator/run` | POST | 触发一次审查，返回新报告 |
| `/api/curator/reports?limit=` | GET | 报告列表（不含建议正文，`limit` 默认 20 上限 50） |
| `/api/curator/reports/{id}` | GET | 单份报告详情（含建议） |
| `/api/curator/reports/{id}/apply` | POST | 应用建议；body `{"suggestion_ids":[...]}` 或 `{"all":true}` |
| `/api/curator/reports/{id}/dismiss` | POST | 忽略建议；body 同上 |

请求/响应仅含白名单字段；`apply`/`dismiss` 是唯二的写操作。审查运行期间目标数据若已被外部改动（如用户刚删了某记忆），`apply` 时按 id 缺失静默跳过并返回实际应用数。

## 8. 前端

侧栏新增「审查」入口，新增 `curator` 视图 + `CuratorPage` + API 客户端：

- 顶部「立即审查」按钮（调 `/api/curator/run`，运行中显示加载态）。
- 报告列表（时间 + scope + 状态 + 建议数）。
- 报告详情：建议卡片（kind 标签、`summary`、涉及条目正文现取展示、`keep`/`drop` 高亮），每条「应用」「忽略」，顶部「全部应用」「全部忽略」。
- 应用/忽略后刷新状态；错误显示页面内安全提示与重试。

## 9. 配置（`agent.yaml` 新增 `curator` 节）

| 键 | 默认 | 说明 |
|------|------|------|
| `directory` | `data/curator` | 报告存储目录 |
| `merge_threshold` | `0.85` | 相似度高于此值判重复 |
| `conflict_threshold` | `0.45` | 相似度低于此值判无关 |
| `enable_llm` | `true` | 是否启用 LLM 冲突精判 |
| `max_pairs_per_run` | `200` | 单次审查候选对上限 |
| `max_reports` | `50` | 保留报告数 |

`CuratorSettings`（`config/settings.py`）对应新增，默认值即可用。

## 10. 隐私与安全

- 审查只读运行，产出建议，不自动删改；apply 是显式用户动作。
- LLM 精判仅发送条目文本，不发送工具参数、工具结果、环境变量、密钥、会话原文。
- embedding 走本地 Ollama（`bge-m3`），数据不出本机。
- 报告只存条目 id + 一句话 summary，不重复落盘条目正文。
- apply/dismiss 日志不记录条目正文与原始异常。

## 11. 测试与验收

后端覆盖：

- 候选生成：同 category / 同字段配对、`max_pairs_per_run` 截断、空数据返回空报告。
- 相似度：模拟 embedder 返回向量，验证 `merge`/无关/精判区间的分桶正确。
- LLM 精判：`duplicate`/`conflict`/`unrelated` 三种输出映射到建议；`enable_llm=false` 跳过。
- 降级：embedder 抛错时退化为字符重叠度，curator 不崩溃。
- 服务：`run` 只读不落任何数据变更；`apply` 复用 MemoryService/ProfileService 正确删改，目标 id 缺失时跳过；`dismiss` 状态流转。
- API：run/列表/详情/apply/dismiss 的字段白名单、404、参数校验；报告不泄露条目正文以外的敏感内容。

前端覆盖：

- 审查页列表、建议卡片渲染、应用/忽略交互、空态与错误重试、导航接入。

验收标准：手动触发审查能在前端看到可读的重复/冲突建议，逐条或批量应用后记忆/画像被正确去重；审查过程不修改数据、不泄露敏感内容；Ollama 不可用时仍能做确定性去重。
