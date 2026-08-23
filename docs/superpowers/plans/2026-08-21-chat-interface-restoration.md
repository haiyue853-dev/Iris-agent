# Iris 聊天界面恢复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 恢复居中、响应式的 Iris 聊天界面，并在现有 assistant-ui 运行时上补齐附件、思考状态、工具状态和来源引用等核心聊天体验。

**架构：** 先从 CSS 级联根因入手，把全局 reset 放入 Tailwind 基础层；随后让 `irisRuntime` 在单一适配边界输出 assistant-ui 可消费的规范化消息 parts。`Thread` 只组合专注的展示组件，继续复用现有会话、附件上传和工具审批数据流。

**技术栈：** React 19、TypeScript、Vite 8、Tailwind CSS 4、assistant-ui、Vitest、Testing Library

---

## 文件结构

- 修改 `web-react/src/index.css`：声明 Tailwind 主题与分层的基础 reset。
- 修改 `web-react/src/App.css`：移除会覆盖 Tailwind utilities 的未分层通配 reset。
- 创建 `web-react/tests/ChatLayout.theme.test.ts`：静态验证 CSS 分层和聊天布局关键类。
- 修改 `web-react/src/lib/irisRuntime.ts`：把 Iris 消息/事件转换为 text、reasoning、tool、source 和 attachment parts。
- 修改 `web-react/src/components/assistant-ui/thread.tsx`：组合聊天核心状态组件并恢复可访问文案。
- 创建 `web-react/src/components/assistant-ui/reasoning.tsx`：可折叠思考区与流式动画。
- 创建 `web-react/src/components/assistant-ui/sources.tsx`：安全、紧凑的来源列表。
- 修改 `web-react/src/components/assistant-ui/tool-fallback.tsx`：统一工具运行中、审批、成功和失败状态。
- 修改 `web-react/src/components/assistant-ui/attachment.tsx`：统一 composer 与消息附件的核心展示。
- 创建 `web-react/src/components/assistant-ui/thread.test.tsx`：验证核心消息状态的渲染。

### 任务 1：修复 CSS 层级和聊天布局

**文件：**
- 创建：`web-react/tests/ChatLayout.theme.test.ts`
- 修改：`web-react/src/index.css`
- 修改：`web-react/src/App.css`

- [ ] **步骤 1：编写失败的 CSS 回归测试**

```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("chat layout CSS layering", () => {
  const indexCss = readFileSync(resolve("src/index.css"), "utf8");
  const appCss = readFileSync(resolve("src/App.css"), "utf8");

  it("keeps the global reset inside Tailwind base layer", () => {
    expect(indexCss).toMatch(/@layer base\s*\{[\s\S]*\*\s*\{/);
    expect(appCss).not.toMatch(/^\s*\*\s*\{/m);
  });

  it("keeps the main shell constrained to the viewport", () => {
    expect(appCss).toContain("min-width: 0");
  });
});
```

- [ ] **步骤 2：运行测试并确认因未分层 reset 失败**

运行：`npm test -- tests/ChatLayout.theme.test.ts`

预期：FAIL，`index.css` 不含 `@layer base` reset，且 `App.css` 仍包含顶层 `*` 规则。

- [ ] **步骤 3：实施最小 CSS 修复**

在 `index.css` 的 `@theme` 后加入：

```css
@layer base {
  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  html,
  body,
  #root {
    width: 100%;
    height: 100%;
  }

  body {
    margin: 0;
  }
}
```

从 `App.css` 删除顶层通配 margin/padding reset，并给 `.main-content` 增加：

```css
min-width: 0;
```

- [ ] **步骤 4：运行回归测试与现有壳层测试**

运行：`npm test -- tests/ChatLayout.theme.test.ts tests/Sidebar.theme.test.ts`

预期：全部 PASS。

- [ ] **步骤 5：浏览器检查根因已消失**

在 `1280×720` 视口读取 `.aui-thread-welcome-root` 与 `.aui-thread-viewport-footer` 的 bounding box。

预期：二者宽度不超过 `704px`，且 `x` 大于 `.main-content.x`；页面无横向溢出。

### 任务 2：规范化思考、工具和来源消息 parts

**文件：**
- 修改：`web-react/src/lib/irisRuntime.ts`
- 创建：`web-react/src/lib/irisRuntime.parts.test.ts`

- [ ] **步骤 1：为既有事件形状添加失败测试**

```ts
import { describe, expect, it } from "vitest";
import { toThreadMessages } from "./irisRuntime";

describe("toThreadMessages rich parts", () => {
  it("preserves reasoning and sources as typed parts", () => {
    const [message] = toThreadMessages([{
      id: "m1",
      role: "assistant",
      content: "结论",
      reasoning: "正在分析",
      sources: [{ title: "参考资料", url: "https://example.com/doc" }],
    } as never]);

    expect(message.content).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "reasoning", text: "正在分析" }),
      expect.objectContaining({ type: "source", url: "https://example.com/doc" }),
      expect.objectContaining({ type: "text", text: "结论" }),
    ]));
  });
});
```

- [ ] **步骤 2：运行测试确认转换边界丢失富消息信息**

运行：`npm test -- src/lib/irisRuntime.parts.test.ts`

预期：FAIL，输出中缺少 reasoning 或 source part。

- [ ] **步骤 3：在 adapter 边界实现最小映射**

新增专用转换函数，顺序固定为 reasoning、tool/source、text、attachments；未知字段保持忽略，现有 tool-call 映射和审批 callId 不变。只使用 `types.ts` 中实际存在的字段；若后端当前未提供 reasoning/sources，则新增可选字段并保持旧数据兼容。

- [ ] **步骤 4：运行 runtime 和 hook 测试**

运行：`npm test -- src/lib/irisRuntime.parts.test.ts src/hooks/useChat.task.test.tsx src/hooks/useChat.attachments.test.tsx`

预期：全部 PASS。

### 任务 3：增加核心聊天展示组件

**文件：**
- 创建：`web-react/src/components/assistant-ui/reasoning.tsx`
- 创建：`web-react/src/components/assistant-ui/sources.tsx`
- 修改：`web-react/src/components/assistant-ui/tool-fallback.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`
- 创建：`web-react/src/components/assistant-ui/thread.test.tsx`

- [ ] **步骤 1：编写失败的渲染测试**

```tsx
it("renders reasoning, sources and tool status near assistant content", () => {
  render(<RichPartFixtures />);
  expect(screen.getByRole("button", { name: /思考过程/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "参考资料" })).toHaveAttribute(
    "href",
    "https://example.com/doc",
  );
  expect(screen.getByText("工具运行中")).toBeInTheDocument();
});
```

- [ ] **步骤 2：运行测试确认组件尚不存在**

运行：`npm test -- src/components/assistant-ui/thread.test.tsx`

预期：FAIL，缺少思考区、来源链接或工具状态文案。

- [ ] **步骤 3：实现可折叠思考区**

`reasoning.tsx` 使用原生 button + region，提供 `aria-expanded` 和 `aria-controls`；运行中显示三个使用 CSS 动画的点，`prefers-reduced-motion` 下禁用动画。默认运行中展开、完成后折叠。

- [ ] **步骤 4：实现安全来源列表**

`sources.tsx` 仅接受 `http:`/`https:` URL；链接使用 `target="_blank" rel="noreferrer noopener"`，标题为空时展示 URL hostname，空数组返回 `null`。

- [ ] **步骤 5：统一工具状态与 Thread 组合**

在 `tool-fallback.tsx` 将状态映射为“工具运行中 / 等待批准 / 已完成 / 执行失败”，保留现有 `IrisChatContext.resolveApproval`。在 `thread.tsx` 的 assistant message part components 中注册 reasoning、source 与 tool renderer，不在组件内读取原始 SSE 事件。

- [ ] **步骤 6：运行组件测试**

运行：`npm test -- src/components/assistant-ui/thread.test.tsx src/components/ChatContainer.approval.test.tsx`

预期：全部 PASS，且无 React act 警告。

### 任务 4：完善附件与响应式行为

**文件：**
- 修改：`web-react/src/components/assistant-ui/attachment.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`
- 修改：`web-react/src/hooks/useChat.attachments.test.tsx`
- 修改：`web-react/src/components/MessageBubble.attachments.test.tsx`

- [ ] **步骤 1：补充附件展示失败测试**

断言 composer 附件具有可访问名称和移除按钮；已发送图片显示缩略图，普通文件显示文件名；零附件时不渲染空容器。

- [ ] **步骤 2：运行附件测试确认缺失行为**

运行：`npm test -- src/hooks/useChat.attachments.test.tsx src/components/MessageBubble.attachments.test.tsx`

预期：新增断言至少一项 FAIL，失败原因对应缺失的附件呈现行为。

- [ ] **步骤 3：实施最小附件 UI 调整**

复用现有 assistant-ui attachment primitives：composer 使用紧凑 inline/grid 预览，用户消息使用 grid/list 预览；移除按钮仅在 composer attachment 可用；错误附件显示状态文案但保留文件名。

- [ ] **步骤 4：运行附件与 Thread 测试**

运行：`npm test -- src/hooks/useChat.attachments.test.tsx src/components/MessageBubble.attachments.test.tsx src/components/assistant-ui/thread.test.tsx`

预期：全部 PASS。

### 任务 5：全量验证和视觉验收

**文件：**
- 仅在验证发现明确回归时修改上述文件。

- [ ] **步骤 1：运行完整测试**

运行：`npm test`

预期：0 个失败。

- [ ] **步骤 2：运行 lint**

运行：`npm run lint`

预期：退出码 0；如存在与本次无关的既有警告，记录文件与规则，不扩大修改范围。

- [ ] **步骤 3：运行生产构建**

运行：`npm run build`

预期：退出码 0；允许现有 bundle-size 警告，不允许 TypeScript 或 CSS 构建错误。

- [ ] **步骤 4：桌面浏览器验收**

在 `1280×720` 检查欢迎区居中、建议卡片两列、composer 完整、附件按钮可见、无页面横向溢出。

- [ ] **步骤 5：窄屏浏览器验收**

在约 `390×844` 检查建议卡片单列、消息和 composer 不被裁切、附件可滚动或换行、无页面横向溢出。

- [ ] **步骤 6：检查最终差异**

运行：`git diff --check`（仅当工作区恢复为 Git 仓库）；否则使用 `rg` 与逐文件检查确认无调试代码、占位符或意外生成文件。

## 提交说明

当前 `D:\agent\Iris-agent` 不是有效 Git 仓库，所以计划执行期间不运行 `git add` 或 `git commit`。若仓库元数据恢复，则每个任务验证通过后分别提交，建议提交信息依次为：

```text
fix: restore assistant chat layout
feat: map rich assistant message parts
feat: render reasoning tools and sources
feat: refine chat attachments
test: verify restored chat experience
```
