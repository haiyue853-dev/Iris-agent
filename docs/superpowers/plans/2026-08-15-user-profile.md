# 实现计划：用户建模 / 画像（一期）

日期：2026-08-15
分支：feature/user-profile

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | 画像模型 + 存储 | `profile/models.py` + `profile/repository.py` |
| 2 | 画像提取器 | `profile/extractor.py`（LLM 提取增量） |
| 3 | 画像服务 | `profile/service.py`（merge/render/节流） |
| 4 | Agent 注入 + 自动提取触发 | `core/agent.py` |
| 5 | 配置 + 装配 + API + 全量验证 | `settings.py` + `bootstrap.py` + `api/profile_api.py` |

（一期纯后端，不做前端画像页面，节省范围与 token）

## 任务细节

### 任务 1：画像模型 + 存储
- `UserProfile` / `ProfilePatch` 数据类；`ProfileRepository`（`data/profile/profile.json`，原子写 + 锁）。
- 测试：`tests/profile/test_repository.py`。

### 任务 2：画像提取器
- `ProfileExtractor(provider)`：`extract(dialogue: str) -> ProfilePatch`，用 provider 输出 JSON 并解析；解析失败返回空 patch。
- 测试：`tests/profile/test_extractor.py`（fake provider 返回预设 JSON）。

### 任务 3：画像服务
- `ProfileService(repository, extractor, ...)`：`get` / `apply_patch`（去重 + 截断 + 上限）/ `render`（≤800 字）/ `maybe_update(dialogue)`（节流，默认每 10 轮）。
- 测试：`tests/profile/test_service.py`。

### 任务 4：Agent 注入 + 自动提取
- `AgentService` 加可选 `profile_service` 参数；`_build_messages` 注入画像；`run` 末尾调 `maybe_update`。
- 测试：`tests/core/test_agent_profile.py`。

### 任务 5：配置 + 装配 + API + 全量验证
- `ProfileSettings`（`extract_interval_rounds=10`）；`bootstrap.py` 构造 profile 服务并注入 AgentService；`api/profile_api.py`（GET/PUT）。
- 测试：`tests/api/test_profile_api.py` + 装配测试；后端全量 pytest + 隐私核对；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖模型存储；任务 2 覆盖提取；任务 3 覆盖 merge/注入/节流；任务 4 覆盖 Agent 接入；任务 5 覆盖配置/装配/API/验证。
- 类型一致性：`ProfilePatch` 字段与 `UserProfile` 一致；API 白名单与模型一致。
- 安全边界：提取 best-effort 失败静默；画像只含用户维度，不含工具参数/结果/密钥；PUT 白名单校验 + 截断；节流每 10 轮控制 token。

## 执行结果（2026-08-15）

- 5 个任务全部完成并提交（5 个 commit）：模型存储 → 提取器 → 服务 → Agent 注入+自动提取 → 配置/装配/API。
- 核心实现：`profile/models.py`（UserProfile/ProfilePatch）、`repository.py`（原子写+锁）、`extractor.py`（LLM 提取 JSON 增量，失败静默）、`service.py`（merge/render/节流每 10 轮 + replace）、`core/agent.py`（注入画像 + run 末尾 maybe_update）、`api/profile_api.py`（GET/PUT）、`ProfileSettings`。
- 全量验证：后端 `422 passed, 3 skipped, 0 failed`（新增 31 条画像测试全绿）。
- 隐私核对：画像只含用户维度，提取 best-effort 失败不影响主对话，PUT 白名单校验 + 截断。

