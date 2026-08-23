# Iris Agent 竞争力分析

- 文档版本：v1
- 编制日期：2026-08-23
- 适用代码版本：`main` 分支（最近一次完整测试：后端 537 passed / 3 skipped，前端 116 passed）

---

## 0. 整体定位（先说清坐标系）

`Iris Agent` 是一个**单进程 Python + React 个人 AI 工作台**，定位介于 *Dify/FastGPT*（企业 RAG/Bot 平台）和 *Cursor/Cline*（编程 Agent）之间。功能面很广（12 个工作台视图、537 后端测试通过），但深度上很多模块还是"能跑"而非"强"。

主要参考对象：
- `hermes-agent/`（直接对标的架构样板）
- `assistant-ui/`、`tool-ui/`（参考前端工程）
- `open-webui-main/`（同类个人 Chat 工作台）

---

## 1. 明显缺失的"门槛级"能力（竞争对手都有）

### 1.1 写文件 / 改文件 / 跑命令——三大件全部缺失

- [iris_agent.py:1](iris_agent.py#L1) 入口和 [README.md:87](README.md#L87) 明确写：「当前版本不提供写文件、删除或 Shell 执行工具」。
- [iris_agent/tools/builtin/files.py](iris_agent/tools/builtin/files.py) 里只有 `read_file` 和 `list_directory`。
- **后果**：Agent 不能改自己工作区、不能跑测试、不能 `git diff`、不能落盘长报告。相当于不能做"开发型"任务，只能"问答型"任务。Cursor / Cline / Continue / Claude Code 全都靠这三件起家。

### 1.2 没有任何代码执行沙箱

- 没有 `code_execute` / `python_run` / `repl` 类工具。
- 子代理（[iris_agent/subagent/runner.py](iris_agent/subagent/runner.py)）也只是再跑一遍 `AgentLoop`，不会产出可执行产物。
- 对比：Dify 的「代码节点」、Coze 的「代码沙箱」、Hermes 的 Hermes-2 都是核心。

### 1.3 多模态只到"读"，缺"理解"和"生成"

- [iris_agent/tools/builtin/attachments.py](iris_agent/tools/builtin/attachments.py) 只能 `read_attachment` 文本。
- [README.md:28](README.md#L28) 提到「图片 OCR 属于可选本机能力」但**没接入任何视觉模型**。
- Provider 层（[iris_agent/providers/openai_compat.py](iris_agent/providers/openai_compat.py)）没有处理 `image_url` content type——给 GPT-4o/Claude 多模态会直接丢图。
- **没有图像生成**（DALL·E / SD / Imagen）。

### 1.4 远程 / HTTP MCP 完全没有

- [iris_agent/mcp_center/service.py](iris_agent/mcp_center/service.py) 只支持本地 stdio。
- [PROJECT_STATUS.md:109](PROJECT_STATUS.md#L109) 也明确这是已知问题：「尚未支持远程 HTTP/SSE MCP 服务、多用户隔离或集中式凭据管理」。
- 现代生态（Cursor、Claude Desktop、ChatGPT）几乎默认 HTTP MCP。

### 1.5 用户体系 / 鉴权 / 多租户

- 整个 `iris_agent/api/` 没有 `Depends(get_current_user)` 类装饰器，没有登录页。
- 聊天是单租户 JSON 文件，会话前缀是 `gateway`。
- 企业场景不可用。

### 1.6 移动端

- [web-react/src/components/Sidebar.tsx:22-28](web-react/src/components/Sidebar.tsx#L22-L28) 写死 `window.innerWidth <= 720` 自动折叠——没有真正响应式布局，没有 PWA，没有 App。

---

## 2. 已经做了但"不够强"的模块

### 2.A 记忆系统（P1）—— 基本是"纸条本"

- [iris_agent/memory/models.py:14](iris_agent/memory/models.py#L14) 单条最大 500 字符、4 个固定类别（preference/fact/project/other）、最多 500 条、注入上限 2000 字符。
- 没有 embedding、没有时间衰减、没有遗忘曲线、没有关联、没有"何时不应注入"的去重策略。
- Hermes 的 MemRL / MemGPT、ChatGPT 的 `memory` 都是有向图 + 反思机制。
- **建议**：要么把"类别 4 类 + 500 字"扩到"实体-关系-事件"模型，要么直接和知识库合并。

### 2.B 知识库——平面条目，无文档集

- [iris_agent/knowledge/service.py:836-852](iris_agent/knowledge/service.py#L836-L852) `add(title, content)` 是"一条=一篇文档"，没有"文档→段落→句子"切分。
- [iris_agent/knowledge/retriever.py](iris_agent/knowledge/retriever.py) 的 HybridRetriever 跑在整段 `entry.content` 上，文档一大召回就糊。
- 缺：文件上传→解析→切片、向量化；缺 rerank；缺"按来源追溯"UI。
- 对比 Dify / FastGPT 的知识库工作台：差距在「文档管线」上。

### 2.C Skill 中心——本质是 prompt 模板

- [iris_agent/skill_center/service.py](iris_agent/skill_center/service.py) `save_user_skill(name, description, content)`——只有名字+描述+正文。
- 没有结构化步骤（像 Anthropic Skills 的 `scripts/`、`references/`、`assets/`）、没有参数化输入、没有输出 schema、没有版本。
- [iris_agent/skill_center/bundled/web-research/SKILL.md](iris_agent/skill_center/bundled/web-research/SKILL.md) 写得很好但**Skill 不能调用 Skill**、**不能组合**——只是给 LLM 看的指令。

### 2.D 子代理——单层委派，无协作

- [iris_agent/subagent/runner.py](iris_agent/subagent/runner.py) `run_parallel` 顶多 5 个并发，每个都跑同一个 `AgentLoop`。
- 没有 Plan-Verify-Refine、没有"代理 A 写→代理 B 审→代理 C 改"的工作流。
- 没有跨代理消息、共享 memory、状态合并。
- 对比 LangGraph / AutoGen：Iris 子代理是"扁平委派"，不是"图编排"。

### 2.E 任务队列——单 Worker

- [iris_agent/task_queue/service.py](iris_agent/task_queue/service.py) 显式注释：`Run persisted jobs FIFO, allowing at most one Agent request at a time.`
- 用户长任务一多就堵。没有优先级、没有抢占、没有 worker 池。
- 实际 Chat 体验：第二个用户发消息要等第一个跑完。

### 2.F 上下文压缩触发点过低

- [agent.yaml:103-106](agent.yaml#L103-L106) `trigger_chars: 12000`，主流模型（DeepSeek 64k、Claude 200k、Gemini 1M）窗口都大得多。
- 12000 字符≈4k token 就压缩，会"过度摘要"——损失细节、影响工具结果追溯。
- 没有"按消息类型压缩"（系统消息/工具消息保留更长）。

### 2.G 用户画像——4 字段 + 简单 LLM 抽取

- [iris_agent/profile/models.py](iris_agent/profile/models.py) 只有 `preferences / goals / style / facts`。
- [iris_agent/profile/extractor.py](iris_agent/profile/extractor.py) 注释是 LLM 抽取——但每 10 轮才跑一次（[agent.yaml:99](agent.yaml#L99) `extract_interval_rounds: 10`）。
- 没有实体图、没有"我朋友叫 XXX"这类关系建模。
- **更严重**：被 LLM 摘要压缩时，画像本身也会被当作"消息"压缩掉——自我遗忘。

### 2.H 任务中心（MCP 安全活动是同问题）

- [PROJECT_STATUS.md:108](PROJECT_STATUS.md#L108) 自己承认：「MCP 活动不是长期审计日志，仅保留最近 50 条」。
- [iris_agent/task_center/service.py:15-19](iris_agent/task_center/service.py#L15-L19) `MAX_TASKS = 100, MAX_EVENTS = 100`——能用，但合规审计、历史回溯、分析都做不了。

### 2.I 设置（Settings）面板——刚搭起来

- [iris_agent/settings_profiles/](iris_agent/settings_profiles/) 目录是后来加的，[web-react/src/api/settings.ts](web-react/src/api/settings.ts) 也较新。
- [web-react/src/components/settings/SettingsModal.tsx](web-react/src/components/settings/SettingsModal.tsx) 只做"切 API Profile"——没有"模型参数面板（温度/超时/重试）""每个工具的启用矩阵""记忆/压缩策略可视化"。

### 2.J 工具调用体验

- [web-react/src/components/tool-ui/](web-react/src/components/tool-ui/) 有 approval-card / shared / terminal，但 [web-react/src/components/assistant-ui/tool-fallback.tsx](web-react/src/components/assistant-ui/tool-fallback.tsx) 还在 `assistant-ui/` 目录里——UI 切到自定义，但 fallback 还是占位。
- 没有工具调用计时可视化、没有 token 消耗展示、没有"重试该步骤"按钮、没有"从这步 fork"。

---

## 3. 架构性弱点

### 3.1 JSON 文件当数据库

- 几乎所有 `*_repository.py` 都是 `json.dump` → atomic rename。
- 单进程 OK，但**横向扩展**就崩；多文件之间没有事务（如 `task_queue` + `task_center` 同步靠 `_condition`）。
- 对比：Drizzle、SQLite（甚至单文件 SQLite）能解决 80% 场景又轻量。

### 3.2 Bootstrap 是"上帝模块"

- [iris_agent/bootstrap.py](iris_agent/bootstrap.py) 380+ 行，串了 30+ 服务。
- 加新模块就要改这里——缺少 IoC / DI / 插件注册表。
- 对比 Hermes 用的「Provider/Registry」模式（[reference-hermes-tool-pattern.md](reference-hermes-tool-pattern.md) 已有记忆——值得推而广之到所有子系统，不只 tools）。

### 3.3 没有任何可观测性

- 没有任何 `prometheus_client`、OTel、tracing。
- `logger` 只是 stdlib logging。
- 用户卡住时你也不知道：LLM 慢？工具循环？上下文撑爆？全靠人肉查日志。

### 3.4 没有"prompt 版本管理" / "A/B 框架"

- [agent.yaml:13-23](agent.yaml#L13-L23) `system_prompt` 是一坨写在 YAML 里的中文——改了不留历史、不分版本、不分用户。
- 也没有"两个 prompt 跑同样 query 对比"的能力。

### 3.5 CI/CD 几乎没有

- 工作区根目录 `Is a git repository: false`——仓库根目录没有 `.git`，项目本身没有版本控制可见。
- 也没有 `.github/workflows/`、`Dockerfile`、`docker-compose.yml`。
- 部署靠 `python server.py`——生产化门槛没跨过。

---

## 4. UI/UX 竞争力差距

按"和 ChatGPT / Claude.ai / 扣子 / Dify 用户体验对比"找：

1. **没有 message 编辑 / regenerate / fork**——发错了只能整轮重来。
2. **没有消息树（branching conversations）**——Cursor 都有了。
3. **没有暗/亮主题切换**——[web-react/src/App.css](web-react/src/App.css) 写死了 Iris 主题。
4. **没有拖拽文件**——靠 [web-react/src/components/AttachmentChip.tsx](web-react/src/components/AttachmentChip.tsx) 手动点。
5. **没有语音输入 / TTS**——浏览器其实自带 `SpeechRecognition`。
6. **没有 markdown 内的 Mermaid 实时渲染**——UML 单独建画布是过度设计，聊天里 `mermaid` 代码块渲染成图才是基本。
7. **没有代码块高亮**（`react-syntax-highlighter` 没看到）。
8. **没有对话导出**（JSON/Markdown/HTML）。
9. **没有分享对话**（公开链接、只读视图）。
10. **没有"插件市场"视图**——MCP 服务都堆在一个表里。

---

## 5. 优先级建议（如果只做 5 件事）

按"用户感知最强 / 实现成本可控"排序：

| 优先级 | 任务 | 理由 | 大致成本 |
|---|---|---|---|
| **P0** | 补齐写文件 / 改文件 / Shell 三个工具 + 工作区权限沙箱 | 决定 Agent 是"问答"还是"干活" | 中（含审批与路径越界） |
| **P0** | 接多模态（视觉理解 + 可选图像生成） | 主流模型标配，缺了就显得过时 | 低（OpenAI 兼容已就位） |
| **P1** | 文档知识库改造：上传→解析→切片→向量化→rerank | RAG 是知识库的灵魂，目前只是关键词 | 中 |
| **P1** | 远程 HTTP/SSE MCP + OAuth | MCP 是 2025+ 生态的事实标准 | 中 |
| **P1** | 子代理工作流（plan-verify-refine / DAG） | 让 SubagentRunner 从"扁平"变"图编排" | 中高 |
| **P2** | 记忆系统升级为"实体-关系-事件" | 现有 4 类别+500 字太弱 | 高（需重写） |
| **P2** | SQLite 替换 JSON + 加迁移 | 横向扩展 / 多用户 / 一致性的地基 | 中 |
| **P2** | 暗/亮主题 + 编辑/重发/分支 | 跟 ChatGPT 看齐的 UX 底线 | 低 |
| **P3** | 鉴权 + 多用户 | 企业场景必须 | 高 |
| **P3** | Skill 中心结构化（步骤+参数+版本） | 跟 Anthropic Skills 对齐 | 中 |

---

## 6. 一句话总结

**「广度已经能打 Dify 个人版；深度差在『写/改/跑/视觉/远程 MCP/多租户/可观测性』上。」**

补齐这 5 块（写工具、视觉、文档 RAG、远程 MCP、子代理工作流），Iris Agent 就能从"个人玩具"跨到"个人 Agent 平台"的门槛。

---

## 7. 附录：已盘点模块一览（避免重复评估）

### 后端核心（`iris_agent/`）
- `core/` AgentLoop / AgentService / cancellation — 单流式 + 单 worker，结构清晰
- `providers/openai_compat.py` — 流式 + 工具调用 OK；缺多模态 content type
- `sessions/` JSON 仓储
- `tools/builtin/` — `current_time` / `list_directory` / `read_file` / `remember` / `recall` / `use_skill` / `save_skill` / `delegate_task(s)` / `web_search` / `fetch_page` / `add_knowledge` / `search_knowledge` / `read_attachment`
- `memory/` P1
- `session_search/` P2
- `skill_center/` P3
- `subagent/` P4
- `profile/` 用户画像
- `context_compression/` LLM 摘要
- `web_search/` 联网 + 真浏览器兜底
- `knowledge/` 一期关键词 + 二期 hybrid（Ollama bge-m3）
- `mcp_center/` 本地 stdio
- `aihot_daily/` AI 资讯
- `hot_radar/` + `automation/` + `notifications/`
- `reports/` 日报（多版本 + 附件 + OCR stub）
- `task_center/` + `task_queue/` 任务状态机 + 单 worker 队列
- `curator/` 记忆/画像/技能/知识去重合并
- `gateway/` QQ OneBot + WeCom
- `settings_profiles/` 多 API Key 切换
- `attachments/` 聊天附件 + 提取

### 前端（`web-react/src/`）
- `App.tsx` 视图路由：chat / aihot / uml / reports / skills / automation / radar / mcp / tasks / memory / knowledge / curator
- `hooks/useChat.ts` 后台提交 + 轮询
- `components/aihot/` `automation/` `curator/` `knowledge/` `mcp/` `memory/` `reports/` `skills/` `tasks/` `uml/` `ui/` `assistant-ui/` `tool-ui/`

### 测试覆盖
- 后端：537 passed / 3 skipped
- 前端：116 passed（24 文件）
- `npm run build` 通过
