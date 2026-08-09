# Iris Agent：Skills 中心、文档工作台与热点雷达实现计划

> **面向 AI 代理的工作者：** 必须使用子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟进进度。

**目标：** 为 Iris Agent 增加一个本地优先的个人 Skills 中心，并交付两个首批可用 Skill：文档工作台和热点雷达（含每天一次的本地定时摘要）。

**架构：** Skills 中心只管理受信任的、随 Iris 打包的 `SKILL.md` 元数据与启用状态，不执行任意脚本；文档工作台拥有独立的安全文件库、解析器和草稿；热点雷达复用现有 AI Hot、世界和科技资讯客户端，通过可测试、幂等的应用内调度器生成本地归档摘要。三个模块通过独立服务和 API 接入现有 `ApplicationServices`、FastAPI 与 React 视图。

**技术栈：** Python 3、FastAPI、现有 OpenAI 兼容 Provider、JSON 原子持久化、`python-docx`、`pypdf`、`openpyxl`、`xlrd`、React、TypeScript、Vite、Vitest、React Testing Library。

---

## 0. 范围、依据与不做的事

### 参考依据

- 本地参考源码：`D:\agent\hermes-agent`。重点借鉴其「按需 Skill、受限工具/MCP、持久记忆、定时任务」的组合，而不是一次性安装大量外部工具。
- Iris 现有能力：主对话、AI 日报、UML、AI Hot/世界/科技资讯、模型设置、附件文字提取和 FastAPI/React 框架。
- 现有日报附件仓储 `iris_agent/reports/attachments.py` 有独立的日期、保留和安全生命周期。本计划不重构它，也不把通用文档数据混入日报目录。

### 本次交付范围

1. **Skills 中心**：显示、启停并进入内置 Skill；初始内置卡片为 AI 日报、UML、文档工作台、热点雷达。
2. **文档工作台**：本地上传并解析常见办公文档；选择资料后生成会议纪要、PRD、技术方案或周报；编辑、保存、导出 Markdown/Docx、删除资料。
3. **热点雷达与定时日报**：按关键词和来源订阅，手动或每天定时生成有来源链接的摘要并归档。

### 明确不在本次范围

- 不做任意第三方 Skill 脚本执行、Skill 市场、自动下载安装或通用插件执行器。
- 不做全权限 Shell、桌面自动化或无确认的写操作。
- 不做通用 MCP 连接中心；后续可在已有 Skills 框架之上，以“只读、逐工具授权”的方式接 GitHub/日历/网盘 MCP。
- 不做图片 OCR。图片上传若 OCR 未配置，应返回清晰的“暂不可提取文字”状态，而不是假装提取成功。
- 不做付费搜索 API、全网爬虫、邮件/微信推送，或把热点摘要自动写入 AI 日报。第一版由用户确认后复制/导入，避免绕过日报版本控制。
- 不把文档生成改成流式聊天；第一版使用显式加载状态的单次生成，后续可单列为“文档流式生成”任务，避免扩大本轮风险。

## 1. 实施前置条件与安全边界

当前主工作树已有用户未提交的 UML、资讯、日报等改动。执行者必须先保护这些改动，不能为了开始本计划而清空工作区。

- [ ] 运行 `git -C D:\agent\iris-agent status --short`，记录当前基线；运行后端与前端现有验证，记录失败项。
- [ ] 绝不运行 `git reset --hard`、`git checkout --`、`git clean` 或 `git stash`；绝不使用 `git add .` / `git add -A`。
- [ ] 若当前改动中有来源不明的文件，停止并请用户确认哪些改动应进入基线；不能把未知文件提交到本功能分支。
- [ ] 在用户确认的基线提交上创建隔离工作树，例如：

  ```powershell
  git -C D:\agent\iris-agent worktree add D:\agent\iris-agent\.worktrees\skills-documents-radar -b feature/skills-documents-radar <confirmed-baseline-sha>
  ```

- [ ] 后续每个任务只暂存该任务列出的路径，完成一项提交一项。主工作树继续作为用户可运行的版本，不被本计划中的试验修改。

## 2. 目标数据和 API 契约

### 2.1 Skills 中心

每个打包 Skill 都是只读定义目录，例如：

```text
iris_agent/skill_center/bundled/document-workbench/SKILL.md
```

其中 YAML front matter 只允许以下字段：

```yaml
---
id: document-workbench
name: 文档工作台
description: 上传资料并生成可编辑的工作文档
icon: file-text
category: productivity
entry_view: documents
version: 1
---
```

运行时只持久化用户状态到 `data/skills/settings.json`：

```json
{
  "skills": {
    "document-workbench": {"enabled": true, "updated_at": "2026-08-09T12:00:00+00:00"}
  }
}
```

API：

```text
GET /api/skills
GET /api/skills/{skill_id}
PUT /api/skills/{skill_id}/enabled    { "enabled": true }
```

响应不返回服务器绝对路径、`SKILL.md` 任意内容路径或可执行命令。未知 ID、无效 ID、试图访问路径片段时返回稳定的 Iris API 错误。

### 2.2 文档工作台

第一版允许的文件：`.txt`、`.md`、`.docx`、`.pdf`、`.xlsx`、`.xls`。服务端同时核对扩展名和 MIME 白名单；文件使用服务端 UUID 命名，绝不信任客户端文件名作为磁盘路径。

核心模型：

```text
DocumentRecord(id, display_name, suffix, media_type, size_bytes, sha256,
               extraction_status, extraction_error?, excerpt?, created_at, updated_at)
DocumentDraft(id, title, template, document_ids, instructions, markdown,
              citations, revision, created_at, updated_at)
```

其中 `extraction_status` 只能是 `ready | unavailable | failed`。解析文本只在服务端受控存储；列表 API 只返回安全元数据、摘录和状态，不返回真实文件路径或完整原文。

API：

```text
GET    /api/documents
POST   /api/documents                         multipart file
GET    /api/documents/{document_id}
DELETE /api/documents/{document_id}
POST   /api/documents/drafts/generate          { template, document_ids, instructions }
GET    /api/documents/drafts
GET    /api/documents/drafts/{draft_id}
PUT    /api/documents/drafts/{draft_id}        { title, markdown, expected_revision }
GET    /api/documents/drafts/{draft_id}/export?format=markdown|docx
```

生成允许的 `template` 为 `meeting_minutes`、`prd`、`technical_solution`、`weekly_report`。模型提示必须要求只基于已选 `document_ids` 的文字片段作答，并把引用输出为可验证的 `document_id` 加位置（页、段或工作表）；无可用资料时禁止调用模型。

### 2.3 热点雷达

核心模型：

```text
RadarSubscription(id, name, enabled, sources, include_keywords, exclude_keywords,
                  max_items, run_at, timezone, last_run_key?, created_at, updated_at)
RadarItem(id, source, title, summary, url, published_at?, category?)
RadarDigest(id, subscription_id, scheduled_date, generated_at, items,
            model_summary, highlights, source_citations)
```

`sources` 首批仅为 `aihot`、`world`、`tech`；关键词先做不区分大小写的标题与摘要匹配，排除词优先。去重顺序为规范化 URL，再到规范化标题。`max_items` 限定在 1–30。

API：

```text
GET    /api/hot-radar/subscriptions
POST   /api/hot-radar/subscriptions
PUT    /api/hot-radar/subscriptions/{subscription_id}
DELETE /api/hot-radar/subscriptions/{subscription_id}
POST   /api/hot-radar/subscriptions/{subscription_id}/run
GET    /api/hot-radar/digests
GET    /api/hot-radar/digests/{digest_id}
GET    /api/hot-radar/digests/{digest_id}/markdown
```

调度器只在本地保存一份 digest，不调用日报写接口。`last_run_key` 采用 `subscription_id:当地日期:HH:MM`，保证重启和多次 `tick()` 后同一订阅、同一当地日期最多生成一次。

## 3. 预计新增和修改文件

### 共享接线层

- 修改 `iris_agent/config/settings.py`、`agent.yaml`：增加 `SkillSettings`、`DocumentSettings`、`HotRadarSettings`，包括本地目录、文档配额、热点轮询秒数和默认时区。
- 修改 `iris_agent/bootstrap.py`：在 `ApplicationServices` 创建并暴露 `skills`、`documents`、`hot_radar` 服务；服务共用现有 Provider，但不共用报告附件仓储。
- 修改 `iris_agent/api/app.py`：可选地接入三组新路由，保持目前 `create_app(...)` 的既有测试调用兼容。
- 修改 `server.py`：仅真实服务进程启动/停止 `HotRadarScheduler`；`TestClient(create_app(...))` 不创建后台线程。
- 修改 `web-react/src/App.tsx`、`web-react/src/components/Sidebar.tsx`、`web-react/src/types.ts`、`web-react/src/App.css`：添加 `skills`、`documents`、`radar` 视图和共享主题样式，不改变现有聊天、日报、UML 和资讯入口行为。

### Skills 中心

- 新建 `iris_agent/skill_center/__init__.py`、`models.py`、`catalog.py`、`repository.py`、`service.py`、`errors.py`。
- 新建四个目录和定义：
  - `iris_agent/skill_center/bundled/daily-report/SKILL.md`
  - `iris_agent/skill_center/bundled/uml/SKILL.md`
  - `iris_agent/skill_center/bundled/document-workbench/SKILL.md`
  - `iris_agent/skill_center/bundled/hot-radar/SKILL.md`
- 新建 `iris_agent/api/skills_api.py`、`iris_agent/api/skills_schemas.py`。
- 新建 `tests/skill_center/test_catalog.py`、`tests/skill_center/test_service.py`、`tests/api/test_skills.py`。
- 新建 `web-react/src/api/skills.ts`、`web-react/src/hooks/useSkills.ts`、`web-react/src/components/skills/SkillsPage.tsx`、`SkillCard.tsx` 与对应测试。

### 文档工作台

- 新建 `iris_agent/documents/__init__.py`、`models.py`、`errors.py`、`repository.py`、`storage.py`、`extraction.py`、`prompts.py`、`service.py`。
- 新建 `iris_agent/api/documents_api.py`、`iris_agent/api/documents_schemas.py`。
- 新建 `tests/documents/test_storage.py`、`test_extraction.py`、`test_service.py`、`tests/api/test_documents.py`。
- 新建 `web-react/src/api/documents.ts`、`web-react/src/hooks/useDocuments.ts`、`web-react/src/components/documents/DocumentWorkbenchPage.tsx`、`DocumentLibrary.tsx`、`DocumentComposer.tsx`、`DocumentPreview.tsx` 与对应测试。

### 热点雷达

- 新建 `iris_agent/hot_radar/__init__.py`、`models.py`、`errors.py`、`repository.py`、`sources.py`、`prompts.py`、`service.py`、`scheduler.py`。
- 新建 `iris_agent/api/hot_radar_api.py`、`iris_agent/api/hot_radar_schemas.py`。
- 新建 `tests/hot_radar/test_repository.py`、`test_service.py`、`test_scheduler.py`、`tests/api/test_hot_radar.py`。
- 新建 `web-react/src/api/hotRadar.ts`、`web-react/src/hooks/useHotRadar.ts`、`web-react/src/components/radar/HotRadarPage.tsx`、`SubscriptionEditor.tsx`、`DigestList.tsx`、`DigestPreview.tsx` 与对应测试。

## 4. 实施任务

### 任务 1：建立干净基线、配置和服务接线

- [ ] 先按“实施前置条件”建立隔离工作树；不要修改主工作树的未知改动。
- [ ] 在 `tests/config/test_settings.py` 和新增 `tests/test_bootstrap_services.py` 先写红灯测试：默认设置产生三个安全的本地目录；`build_services()` 创建 `skills`、`documents` 和 `hot_radar`；原有日报/聊天服务仍存在。
- [ ] 运行：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests\config\test_settings.py tests\test_bootstrap_services.py -q
  ```

  预期：实现前因缺少新配置/服务字段而失败。

- [ ] 最小实现 `SkillSettings`、`DocumentSettings`、`HotRadarSettings`，并在 `agent.yaml` 提供清晰、可修改的默认目录；目录都在 Iris 的 `data` 根目录下。
- [ ] 在 `bootstrap.py` 实例化服务，通过依赖注入传递 Provider、配置和受控数据路径；在 `api/app.py` 采用可选参数，避免现有 API 测试构造方式断裂。
- [ ] 重新运行上述测试，预期全部通过；再运行 `python -m pytest tests/api/test_app.py -q`，预期通过。
- [ ] 提交仅限配置、bootstrap、app 接线和这两个测试：

  ```powershell
  git add iris_agent/config/settings.py agent.yaml iris_agent/bootstrap.py iris_agent/api/app.py tests/config/test_settings.py tests/test_bootstrap_services.py
  git commit -m "feat: wire skills document and radar services"
  ```

### 任务 2：实现受信任的 Skills 目录、状态和 API

- [ ] 在 `tests/skill_center/test_catalog.py` 先写解析测试：四个打包 Skill 都能加载；缺字段、重复 ID、`../bad` ID 或未知 `entry_view` 被拒绝；不允许定义中出现命令或外部路径字段。
- [ ] 在 `tests/skill_center/test_service.py` 先写状态测试：默认启用；切换 `document-workbench` 后重启服务仍保留；未知 ID 抛稳定领域错误。
- [ ] 在 `tests/api/test_skills.py` 先写 API 红灯：列表只含公开元数据，启停后可读取，坏 ID/坏正文返回 4xx 且不泄露路径。
- [ ] 运行：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests\skill_center tests\api\test_skills.py -q
  ```

  预期：先红灯，因为模块和路由不存在。

- [ ] 实现目录扫描时的严格 schema 校验：只从包内固定根目录读 `SKILL.md`；使用白名单 `entry_view`；状态 JSON 用临时文件、fsync、replace 原子写入。运行时不执行 Markdown、front matter 或任何可执行字段。
- [ ] 新增四份最小 `SKILL.md`，其描述与现有 AI 日报/UML 和本计划新增页面一致。
- [ ] 实现 `skills_api.py` 和 Pydantic 请求/响应模型，注册路由。
- [ ] 重跑定向测试，预期全部绿色；再跑 `python -m pytest tests/api -q`，预期既有 API 不回归。
- [ ] 提交仅限 `iris_agent/skill_center/**`、`iris_agent/api/skills_*`、任务 2 的测试和 `app.py` 路由改动：

  ```powershell
  git add iris_agent/skill_center iris_agent/api/skills_api.py iris_agent/api/skills_schemas.py iris_agent/api/app.py tests/skill_center tests/api/test_skills.py
  git commit -m "feat: add trusted skills center catalog"
  ```

### 任务 3：交付 Skills 中心前端入口

- [ ] 先为 `SkillsPage` 写 Vitest 红灯测试：显示四张卡；禁用卡片有明确状态和“启用”操作；点击已启用卡按照 `entry_view` 打开正确页面；加载/失败状态可见。
- [ ] 为 `Sidebar`/`App` 写回归测试：左侧只有一个“Skills”入口；现有“AI 日报”、聊天、UML、每日资讯仍按原行为工作；`iris_active_view` 能持久化新视图。
- [ ] 运行：

  ```powershell
  Set-Location D:\agent\iris-agent\web-react
  & 'C:\Program Files\nodejs\npm.cmd' test -- src/components/skills src/App.test.tsx src/components/Sidebar.test.tsx
  ```

  预期：实现前找不到 Skills 页面或新视图而失败。

- [ ] 实现类型、API 客户端和 `useSkills`；避免把 Markdown 当 HTML 注入。卡片只使用标题、说明、图标名和状态。
- [ ] 实现 `SkillsPage` 与 `SkillCard`。视觉沿用已有 CSS 变量、卡片半径、悬停和焦点样式，不给 AI 日报/UML 额外覆盖主题色。
- [ ] 在 `App.tsx` 中添加 `skills`、`documents`、`radar` view 的受控跳转入口；文档与热点页面可以先显示明确的加载占位，直到后续任务实现。
- [ ] 跑定向测试，再运行：

  ```powershell
  & 'C:\Program Files\nodejs\npm.cmd' run lint
  & 'C:\Program Files\nodejs\npm.cmd' run build
  ```

  预期：两项 exit 0。
- [ ] 提交仅限 `web-react/src/api/skills.ts`、`web-react/src/hooks/useSkills.ts`、`web-react/src/components/skills/**`、`App.tsx`、`Sidebar.tsx`、`types.ts`、相关测试和本任务的 CSS：

  ```powershell
  git add web-react/src/api/skills.ts web-react/src/hooks/useSkills.ts web-react/src/components/skills web-react/src/App.tsx web-react/src/components/Sidebar.tsx web-react/src/types.ts web-react/src/App.css
  git commit -m "feat: add skills center workspace"
  ```

### 任务 4：实现文档安全存储和文字提取

- [ ] 先在 `tests/documents/test_storage.py` 写红灯测试：UUID 文件名、扩展名+MIME 不匹配拒绝、超大小/总量/数量拒绝、`..` 和绝对路径不可访问、删除后元数据与文件同步、重启后可列出。
- [ ] 在 `tests/documents/test_extraction.py` 写红灯测试：TXT/MD、DOCX 段落表格、PDF、XLSX/XLS 工作表均可提取；每种格式受字符和行列上限约束；不支持格式和图片 OCR 未配置时为 `unavailable` 或稳定失败状态。
- [ ] 运行：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests\documents\test_storage.py tests\documents\test_extraction.py -q
  ```

  预期：先红灯。

- [ ] 实现独立 `DocumentRepository` 和 `LocalDocumentExtractor`。存储根目录使用 `resolve()` 校验，服务器端 UUID 文件名、白名单 MIME 映射和文件大小在 I/O 前校验；索引 JSON 用原子 replace 持久化。单用户运行时用服务级锁覆盖配额检查、写入和索引更新；清晰记录该仓储只支持单 Iris 服务进程。
- [ ] 不修改日报 `AttachmentRepository` 或其索引格式；解析逻辑保持文档服务独立，避免日期/保留附件规则混淆。
- [ ] 解析失败也要持久化 `failed` 状态和用户安全的错误文案；API 日后仍可列出并允许删除该资料。
- [ ] 重跑定向测试，预期绿色；运行 `python -m pytest tests/reports -q`，确认日报解析未受影响。
- [ ] 提交仅限 `iris_agent/documents/{models,errors,repository,storage,extraction}.py`、`__init__.py` 和任务 4 测试：

  ```powershell
  git add iris_agent/documents tests/documents/test_storage.py tests/documents/test_extraction.py
  git commit -m "feat: add local document storage and extraction"
  ```

### 任务 5：实现文档生成、草稿、导出和 API

- [ ] 在 `tests/documents/test_service.py` 先写红灯测试：无可用资料不调用 Provider；四种模板形成严格提示；引用只含已选择资料 ID；保存编辑需要匹配 `expected_revision`；旧 revision 返回冲突；Markdown 和 Docx 导出都有正确内容类型。
- [ ] 在 `tests/api/test_documents.py` 先写红灯 API 测试：multipart 上传、安全列表、生成草稿、编辑冲突、下载和删除；响应体不含 `file_name` 以外的服务器路径及原始全文。
- [ ] 运行：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests\documents\test_service.py tests\api\test_documents.py -q
  ```

  预期：先红灯。

- [ ] 实现 `prompts.py` 中固定的四个模板和 JSON 输出 schema，例如：

  ```json
  {"title":"...","markdown":"...","citations":[{"document_id":"...","location":"第 2 页"}]}
  ```

- [ ] 对 Provider 原始结果做严格 JSON 解析和引用白名单校验；模型无效输出统一映射为可显示错误，绝不把未验证内容伪装为引用。
- [ ] 实现草稿 JSON 持久化、revision 乐观锁和 `python-docx` 导出。Docx 导出只写标题与 Markdown 的基础块级格式，第一版不承诺复杂 Markdown 样式保真。
- [ ] 实现并注册 documents API；下载使用受控的内存/响应流，不暴露磁盘路径。
- [ ] 重跑定向测试，预期绿色；再运行 `python -m pytest tests/api -q`。
- [ ] 提交仅限 `iris_agent/documents/{prompts,service}.py`、`iris_agent/api/documents_*`、`bootstrap.py`/`app.py`/`server.py` 的本任务接线及任务 5 测试：

  ```powershell
  git add iris_agent/documents/prompts.py iris_agent/documents/service.py iris_agent/api/documents_api.py iris_agent/api/documents_schemas.py iris_agent/bootstrap.py iris_agent/api/app.py server.py tests/documents/test_service.py tests/api/test_documents.py
  git commit -m "feat: add document drafts and exports"
  ```

### 任务 6：交付文档工作台前端

- [ ] 先写 `DocumentWorkbenchPage` 红灯测试：上传队列显示名称/大小/提取状态；只允许选择 `ready` 的资料生成；四个模板可选；生成期间按钮禁用并有加载文案；草稿可编辑、保存冲突可见、两个导出链接正确。
- [ ] 为删除资料和服务错误写测试：删除前明确确认，删除后从库中消失；失败信息不显示服务器路径。
- [ ] 运行：

  ```powershell
  Set-Location D:\agent\iris-agent\web-react
  & 'C:\Program Files\nodejs\npm.cmd' test -- src/components/documents
  ```

  预期：先红灯。

- [ ] 实现 `documents.ts`、`useDocuments.ts`、资料库/编辑器/预览三个组件。布局采用当前 Iris 三栏工作台的响应式规则；窄容器切换为标签页，不重复引入新的颜色体系。
- [ ] 上传使用 `FormData`；文档内容不直接渲染不可信 HTML，Markdown 预览走现有安全文本渲染策略或先以 `pre-wrap` 展示。
- [ ] 保存采用草稿 `revision`，遇到 409 显示“内容已在其他操作中更新，请刷新后重试”，不静默覆盖。
- [ ] `App.tsx` 的 documents view 改为真实工作台，Skills 卡片能进入该页。
- [ ] 跑定向测试、`npm run lint`、`npm run build`，预期全部 exit 0。
- [ ] 提交仅限 documents 前端文件、`App.tsx`、`types.ts`、相关测试和本任务 CSS：

  ```powershell
  git add web-react/src/api/documents.ts web-react/src/hooks/useDocuments.ts web-react/src/components/documents web-react/src/App.tsx web-react/src/types.ts web-react/src/App.css
  git commit -m "feat: add document workbench UI"
  ```

### 任务 7：实现热点标准化、订阅、摘要与 API

- [ ] 在 `tests/hot_radar/test_service.py` 先写红灯测试，使用假的 AI Hot/世界/科技来源：来源项被规范化；包含词匹配；排除词优先；相同 URL/标题去重；最多保留 `max_items`；没有条目时不调用 Provider。
- [ ] 在 `tests/hot_radar/test_repository.py` 写订阅和 digest 重启持久化测试：ID、时区和 `HH:MM` 严格校验；暂停订阅不运行；删除订阅不删除其他 digest。
- [ ] 在 `tests/api/test_hot_radar.py` 写红灯 API 测试：增改停删订阅、手动运行、读取 digest 和 Markdown；所有来源 URL 原样保留为可点击引用，但 API 不泄露数据目录。
- [ ] 运行：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests\hot_radar\test_repository.py tests\hot_radar\test_service.py tests\api\test_hot_radar.py -q
  ```

  预期：先红灯。

- [ ] 在 `sources.py` 写薄适配器调用现有 `AihotDailyClient`、`WorldNewsClient`、`TechNewsClient`，不复制已有抓取逻辑，也不修改已有资讯页行为。
- [ ] 实现纯 `HotRadarService.run_subscription(subscription_id, now)`：校验订阅、获取来源、过滤、去重、截断、用严格 JSON 提示生成摘要并保存 `RadarDigest`。模型摘要必须引用传入的 item ID/URL，不能构造外部链接。
- [ ] 实现 JSON 仓储与 API。手动运行使用当前时间，但将 `now` 作为服务参数注入以便测试；路由不可因其中一个来源失败而返回半个未标记的成功结果。
- [ ] 重跑定向测试，预期绿色；运行 `python -m pytest tests/api -q`。
- [ ] 提交仅限 `iris_agent/hot_radar/{models,errors,repository,sources,prompts,service}.py`、API 文件、必要接线和任务 7 测试：

  ```powershell
  git add iris_agent/hot_radar iris_agent/api/hot_radar_api.py iris_agent/api/hot_radar_schemas.py iris_agent/bootstrap.py iris_agent/api/app.py tests/hot_radar tests/api/test_hot_radar.py
  git commit -m "feat: add hot radar subscriptions and digests"
  ```

### 任务 8：实现幂等定时器，并只在真实服务器中启用

- [ ] 在 `tests/hot_radar/test_scheduler.py` 先写固定时间红灯测试：
  - `09:29` 不运行 `09:30` 的订阅；
  - `09:30` 运行一次；
  - 同日重复 `tick()`、服务重启后再次 `tick()` 都不重复；
  - 禁用订阅不运行；
  - `Asia/Shanghai` 和有效 IANA 时区以各自当地日期计算。
- [ ] 运行：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests\hot_radar\test_scheduler.py -q
  ```

  预期：先红灯。

- [ ] 实现没有 HTTP/FastAPI 依赖的 `HotRadarScheduler.tick(now)`，由 `ZoneInfo` 转换时区；将“已运行”写入订阅的 `last_run_key`，并在生成前/后通过仓储锁和持久化确保幂等。
- [ ] 在 `server.py` 以 `threading.Event` 管理实际服务进程的轮询线程，读取 `hot_radar.poll_interval_seconds`。关闭服务时设置 Event 并 `join`；应用测试及 `create_app()` 本身不自动启动线程。
- [ ] 重新跑 scheduler 测试，预期绿色；运行 `python -m pytest -q`，预期整个后端测试集通过。
- [ ] 提交仅限 `iris_agent/hot_radar/scheduler.py`、`server.py`、设置/测试和必要的服务小改动：

  ```powershell
  git add iris_agent/hot_radar/scheduler.py iris_agent/hot_radar/service.py iris_agent/hot_radar/repository.py iris_agent/config/settings.py agent.yaml server.py tests/hot_radar/test_scheduler.py
  git commit -m "feat: schedule local hot radar digests"
  ```

### 任务 9：交付热点雷达前端并连接 Skills 卡片

- [ ] 先写红灯组件测试：订阅编辑器校验关键词、来源、多时区和时间；手动生成显示 loading；digest 列表显示日期/状态；预览显示摘要、可点击来源链接、复制 Markdown；停用后按钮状态正确。
- [ ] 写 `App` 回归测试：热点雷达卡片进入 `radar`，返回 Skills 后状态不丢；现有“每日资讯”页面仍保持原功能。
- [ ] 运行：

  ```powershell
  Set-Location D:\agent\iris-agent\web-react
  & 'C:\Program Files\nodejs\npm.cmd' test -- src/components/radar src/App.test.tsx
  ```

  预期：先红灯。

- [ ] 实现 `hotRadar.ts`、`useHotRadar.ts` 和雷达页面三组件。`run` 按钮只有在订阅有效时启用；请求失败保留已有 digest，错误在页面内可见。
- [ ] 告知用户“定时生成 = Iris 服务进程运行期间按时生成”，不承诺 Windows 关机/休眠后补跑；可在后续增加任务计划程序集成。
- [ ] 页面视觉复用现有主题 token，卡片、输入、hover、active、focus 与左侧菜单一致；桌面和窄容器都可用。
- [ ] 跑定向测试、`npm run lint`、`npm run build`，预期全部 exit 0。
- [ ] 提交仅限 radar 前端文件、`App.tsx`、`types.ts`、相关测试和本任务 CSS：

  ```powershell
  git add web-react/src/api/hotRadar.ts web-react/src/hooks/useHotRadar.ts web-react/src/components/radar web-react/src/App.tsx web-react/src/types.ts web-react/src/App.css
  git commit -m "feat: add hot radar workspace"
  ```

### 任务 10：集成验收、文档和合并准备

- [ ] 在隔离工作树运行后端全量验证：

  ```powershell
  D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest -q
  ```

  预期：全部通过；任何新增 warning 都必须说明来源，不能因测试跳过而宣称功能可用。

- [ ] 在 `web-react` 运行：

  ```powershell
  & 'C:\Program Files\nodejs\npm.cmd' test
  & 'C:\Program Files\nodejs\npm.cmd' run lint
  & 'C:\Program Files\nodejs\npm.cmd' run build
  ```

  预期：三项 exit 0。

- [ ] 用 `start.cmd` 或 `start.ps1` 在**同一个隔离工作树**启动前后端，手工验收：
  1. Skills 中心可启停并打开四个卡片；
  2. 上传一份 TXT/DOCX/PDF/XLSX，生成并编辑一份会议纪要，导出 Markdown 与 Docx；
  3. 创建只含一个公开来源的热点订阅，手动生成摘要并验证链接、关键词过滤和归档；
  4. 使用测试时钟或短暂轮询验证同一天不重复生成；
  5. 原有聊天、AI 日报、UML、AI Hot、世界/科技资讯和设置页面均可打开。
- [ ] 运行 `git diff --check <baseline>...HEAD`，预期无空白错误；逐提交检查 staged/file list，确认没有把用户主工作树的无关文件混入。
- [ ] 更新 `README.md` 或新建 `docs/features/skills-documents-hot-radar.md`：说明三个模块、受支持文件、数据目录、OCR 限制、热点来源、时区、定时器必须保持 Iris 运行、隐私与删除方式。
- [ ] 请求独立代码审查，重点检查：上传路径/MIME、JSON 持久化、模型引用约束、调度幂等、后台线程关闭、API 路径泄露、前端主题和响应式。
- [ ] 审查通过后再按既有分支收尾流程决定合并；不要在主工作树有未确认改动时直接 merge。

## 5. 完成定义

- Skills 中心中的 4 个打包 Skill 可显示、启停、进入相应页面；它不执行任意 Markdown 或用户提供的脚本。
- 文档工作台能安全处理六种首批格式，明确显示解析状态，基于选中资料生成四类文档，支持 revision 保存和 Markdown/Docx 导出。
- 热点雷达能从现有三个来源创建关键词订阅、手动生成有引用的摘要、按本地时区每天最多生成一次并持久化。
- 所有 API 不泄露服务器文件路径、原始本地路径或模型密钥；删除入口可删除用户上传的文档。
- 后端 pytest、前端 test/lint/build 和手工启动验收均有实际通过证据。
- 现有聊天、AI 日报、UML 与资讯功能的测试未回归，且本轮没有引入全权限 MCP、Shell 或自动外发行为。

## 6. 后续候选阶段（不与本计划混做）

在这三项稳定后，再按实际使用频率选择一项：

1. **工作记忆与历史检索**：先用 SQLite FTS 搜索对话、日报与文档，所有写入先让用户确认。
2. **只读 MCP 连接中心**：优先 GitHub、日历或网盘，逐服务器、逐工具授权；写操作二次确认。
3. **UML 代码库分析 Skill**：选择本地项目目录，生成架构/调用关系 Mermaid 并保留图版本。
4. **文档/日报流式生成**：复用主页 NDJSON 协议，加入逐字输出与“正在生成”动画，而不是在本轮混入新协议。
