# 知识库实现计划

日期：2026-08-15
分支：feature/knowledge-base

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | 知识模型 + 仓储 | `knowledge/models.py` + `knowledge/repository.py`（每条目一文件，原子写+锁） |
| 2 | 可插拔检索器 + 关键词检索 | `knowledge/retriever.py`（KeywordRetriever 复用 tokenize） |
| 3 | 知识服务 | `knowledge/service.py`（add/list/get/delete/search） |
| 4 | add_knowledge + search_knowledge 工具 | `tools/builtin/knowledge_tools.py` |
| 5 | 配置 + 装配 + REST API | `settings.py` + `bootstrap.py` + `api/knowledge_api.py` + `agent.yaml` |
| 6 | 前端页面 + 全量验证 | `components/knowledge/KnowledgePage.tsx` + 导航 |

## 任务细节

### 任务 1：知识模型 + 仓储
- `KnowledgeEntry` / `KnowledgeSearchHit` 数据类（白名单字段 + to_dict/from_dict）。
- `KnowledgeRepository(root)`：`list()` / `get(id)` / `save(entry)` / `delete(id)`，复用原子写 + msvcrt 锁。
- 测试：`tests/knowledge/test_repository.py`。

### 任务 2：检索器
- `KnowledgeRetriever` Protocol；`KeywordRetriever` 复用 `tokenize` 计算 score。
- 测试：`tests/knowledge/test_retriever.py`。

### 任务 3：知识服务
- `KnowledgeService(repository, retriever, ...)`：`add` / `list` / `get` / `delete` / `search`。
- `add` 生成 id、校验、截断、写文件；`search` 委托 retriever。
- 测试：`tests/knowledge/test_service.py`。

### 任务 4：工具
- `build_add_knowledge_tool(service)` + `build_search_knowledge_tool(service)`，导出。
- 测试：`tests/tools/test_knowledge_tools.py`。

### 任务 5：配置 + 装配 + API
- `KnowledgeSettings`；`bootstrap.py` 构造 service 并注册两个工具；`api/knowledge_api.py`（GET/POST/GET id/DELETE/search）；`app.py` 注册；`server.py` 传参；`agent.yaml` 加 `knowledge` 节 + system prompt 指引。
- 测试：`tests/api/test_knowledge_api.py` + 装配测试。

### 任务 6：前端 + 全量验证
- `KnowledgePage`（列表/详情/添加/删除/提问框）+ `api/knowledge.ts` + `types.ts` 类型 + 导航接入 + 测试。
- 后端全量 pytest + 前端 test/build + 隐私核对；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖模型存储；任务 2 覆盖检索；任务 3 覆盖服务；任务 4 覆盖工具；任务 5 覆盖配置/装配/API；任务 6 覆盖前端与验证。
- 类型一致性：`KnowledgeEntry` 白名单字段与 API/tool 一致；`KnowledgeSearchHit` 与检索返回一致。
- 安全边界：工具与 API 只接受白名单字段；检索只对知识库正文；id 服务生成防路径穿越；原子写 + 锁。

## 执行结果（2026-08-15）

- 6 个任务全部完成并提交：模型仓储 → 检索器 → 服务 → 工具 → 配置/装配/API → 前端页面。
- 提交链：`模型仓储` → `检索器` → `服务` → `工具` → `配置装配API` → `前端页面`。
- 验证：后端全量 **520 passed, 3 skipped, 0 failed**（新增 39 条知识测试）；前端 **116 passed**（24 文件）；`npm run build` 通过。
- 隐私核对：`add_knowledge` 只写白名单字段、不碰工具参数/密钥；检索只对知识库正文；id 由服务生成（`kb-<12hex>` 正则校验），repository 层 `_safe_path` 防路径穿越；存储复用原子写 + msvcrt 锁。
