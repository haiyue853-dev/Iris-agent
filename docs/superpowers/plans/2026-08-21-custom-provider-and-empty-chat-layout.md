# 自定义模型服务与空白聊天布局实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让空白聊天页的输入框居中、开始对话后回到底部，并让自定义 OpenAI 兼容 Base URL、API Key 与模型可保存和测试。

**架构：** 聊天线程只维护一份 Composer，并借助 assistant-ui 的线程空状态条件在居中容器与底部容器间切换。设置功能新增独立的连接测试请求，后端使用临时 OpenAI 客户端验证表单值，不改变正在运行的配置；保存接口继续负责持久化和热更新。

**技术栈：** React 19、TypeScript、assistant-ui、Tailwind CSS v4、Vitest、FastAPI、Pydantic、OpenAI Python SDK、pytest

---

## 文件结构

- 修改 `web-react/src/components/assistant-ui/thread.tsx`：实现空白/对话布局切换并删除建议按钮。
- 修改 `web-react/tests/ChatLayout.theme.test.ts`：覆盖两种输入框位置及建议移除。
- 修改 `web-react/src/types.ts`：声明连接测试请求结果类型。
- 修改 `web-react/src/api/settings.ts`：增加设置连接测试客户端。
- 修改 `web-react/src/components/settings/SettingsModal.tsx`：URL 校验、测试按钮及状态反馈。
- 创建 `web-react/tests/SettingsModal.test.tsx`：覆盖设置表单交互。
- 修改 `iris_agent/api/settings_api.py`：规范化 URL、保持空密钥语义并增加连接测试接口。
- 创建 `tests/api/test_settings_api.py`：覆盖保存、热更新、临时连接测试及安全错误映射。

### 任务 1：聊天输入框自适应布局

**文件：**
- 修改：`web-react/tests/ChatLayout.theme.test.ts`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`

- [ ] **步骤 1：添加失败的结构测试**

在主题结构测试中断言：源码不含 `SUGGESTIONS` 与 `ThreadSuggestions`；空线程分支含 `aui-thread-empty-composer` 和 `Composer`；非空线程底栏含 `aui-thread-active-composer` 和同一个 `Composer`。

- [ ] **步骤 2：运行测试并确认失败**

运行：`npm test -- ChatLayout.theme.test.ts`（工作目录 `web-react`）

预期：FAIL，缺少空白页输入框容器，且英文建议仍存在。

- [ ] **步骤 3：实现最小布局改动**

将 `ThreadWelcome` 改为欢迎语和 `Composer` 的居中组合，使用 `AssistantIf condition={({ thread }) => thread.isEmpty}` 渲染；底部 `ViewportFooter` 内用 `AssistantIf condition={({ thread }) => !thread.isEmpty}` 包裹底部 Composer。删除建议常量、组件及未再使用的 `Button` 导入。空白布局使用带 `min-h`/`justify-center` 的响应式容器，底部布局保留现有 sticky 行为。

- [ ] **步骤 4：运行定向测试确认通过**

运行：`npm test -- ChatLayout.theme.test.ts`

预期：PASS。

### 任务 2：设置保存语义和连接测试后端

**文件：**
- 创建：`tests/api/test_settings_api.py`
- 修改：`iris_agent/api/settings_api.py`

- [ ] **步骤 1：编写失败的 API 测试**

使用 FastAPI `TestClient`、临时 `.env` 与伪造 service/provider/client，覆盖：

- `PUT /api/settings` 将 `https://example.com/v1/` 规范化为 `https://example.com/v1` 并立即更新 client；
- `api_key: ""` 不覆盖 `.env` 或运行时密钥；
- 非 HTTP(S) Base URL 返回 422；
- `POST /api/settings/test` 使用表单新密钥，或在留空时使用现有密钥；
- 测试客户端成功时返回 `{ "ok": true, "code": "connected" }` 且不修改 provider；
- 鉴权、模型不存在、连接异常映射成稳定 code，响应与日志不含密钥。

- [ ] **步骤 2：运行测试并确认失败**

运行：`python -m pytest tests/api/test_settings_api.py -q`

预期：FAIL，因为测试路由和 URL 校验尚不存在，空密钥当前会写入 `.env`。

- [ ] **步骤 3：实现请求模型与纯校验函数**

在 `settings_api.py` 中增加 `SettingsConnectionTest`，以及 `_normalize_base_url(value)`；使用 `urllib.parse.urlparse` 要求 scheme 为 `http`/`https` 且存在 netloc，返回去除末尾 `/` 的地址，无效时抛出 422 安全错误。

- [ ] **步骤 4：修正保存行为**

PUT 只在 API Key 去空格后非空时写入和热更新；Base URL 经过统一规范化后写入和热更新；模型仍按非空值更新。持久化失败继续返回现有安全错误。

- [ ] **步骤 5：实现临时连接测试**

新增 `POST /api/settings/test`。从请求值与当前 provider/client 合并出临时配置，缺少密钥时返回 `missing_api_key`；构造临时 `OpenAI` 客户端并发起一次最小的非流式聊天请求，以验证应用实际依赖的兼容接口。捕获 SDK 的 `AuthenticationError`、`NotFoundError`、`APIConnectionError`、`APIStatusError`，分别返回 `authentication_failed`、`model_unavailable`、`connection_failed`、`provider_error`，不得把原始异常或密钥返回前端。

- [ ] **步骤 6：运行后端定向测试确认通过**

运行：`python -m pytest tests/api/test_settings_api.py -q`

预期：PASS。

### 任务 3：设置页连接测试交互

**文件：**
- 修改：`web-react/src/types.ts`
- 修改：`web-react/src/api/settings.ts`
- 创建：`web-react/tests/SettingsModal.test.tsx`
- 修改：`web-react/src/components/settings/SettingsModal.tsx`

- [ ] **步骤 1：编写失败的组件测试**

mock `fetchSettings`、`updateSettings` 与新增的 `testSettingsConnection`，覆盖：无效 URL 时不发请求并显示中文提示；测试期间按钮禁用；成功显示“连接成功”；API Key 留空时测试 payload 不带 `api_key`；保存时 Base URL 去除末尾斜杠且空密钥不提交。

- [ ] **步骤 2：运行测试并确认失败**

运行：`npm test -- SettingsModal.test.tsx`（工作目录 `web-react`）

预期：FAIL，因为连接测试客户端和按钮尚不存在。

- [ ] **步骤 3：增加前端 API 类型和调用**

增加 `SettingsConnectionResult = { ok: boolean; code: string; message: string }`，并实现 `testSettingsConnection(payload)`，向 `/api/settings/test` 发送 JSON POST 请求。

- [ ] **步骤 4：实现表单校验和反馈**

抽取本地 `normalizeHttpUrl`：只接受带主机名的 HTTP(S) URL并移除末尾斜杠。保存和测试共用该校验。新增独立 `testing` 状态和“测试连接”按钮；测试时保留表单、不保存配置，显示后端中文消息；保存成功后保持现有掩码刷新行为。

- [ ] **步骤 5：运行前端定向测试确认通过**

运行：`npm test -- SettingsModal.test.tsx ChatLayout.theme.test.ts`

预期：PASS。

### 任务 4：全量验证与视觉验收

**文件：**
- 如视觉检查发现小屏样式缺陷，修改：`web-react/src/components/assistant-ui/thread.tsx` 或现有设置样式文件
- 如修正样式，同步修改：`web-react/tests/ChatLayout.theme.test.ts` 或 `web-react/tests/SettingsModal.test.tsx`

- [ ] **步骤 1：运行前端全量测试**

运行：`npm test`（工作目录 `web-react`）

预期：全部测试通过。

- [ ] **步骤 2：运行后端全量测试**

运行：`python -m pytest -q`

预期：全部测试通过。

- [ ] **步骤 3：运行静态检查和生产构建**

运行：`npm run lint`，随后运行 `npm run build`（工作目录 `web-react`）。

预期：无新增 lint 错误，TypeScript 与 Vite 构建成功。

- [ ] **步骤 4：浏览器验证**

启动本地后端和 Vite 前端，在桌面宽度与约 390px 移动端宽度检查：空白页输入框位于欢迎语下方并整体居中；英文示例消失；发送首条消息后输入框稳定停靠底部；设置弹窗可校验 URL、测试连接和保存；页面无横向溢出。

- [ ] **步骤 5：记录验证结果**

在交付说明中列出实际执行的测试数量、lint 结果、构建结果、浏览器视口及任何既有警告。当前工作区不是有效 Git 仓库，因此跳过计划中的 commit，不创建或修改版本历史。
