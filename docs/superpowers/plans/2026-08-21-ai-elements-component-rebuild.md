# Iris AI Elements 聊天组件重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 按用户提供的 AI Elements chatbot 代码重构 Iris 聊天展示层，同时保留现有流式运行时、附件、会话和工具审批能力。

**架构：** 继续使用 `assistant-ui` primitives 和 `irisRuntime` 作为真实状态层，在其上建立职责与 AI Elements 对齐的 Conversation、Message、Reasoning、Sources、ToolGroup、PromptInput 和 Suggestions 组件。预览型模型、联网和语音控件仅展示“暂未开放”，不改变请求协议。

**技术栈：** React 19、TypeScript 6、assistant-ui 0.12、Tailwind CSS 4、Lucide React、Vitest、Testing Library、Vite、oxlint。

---

## 文件结构

- 创建 `web-react/src/components/assistant-ui/prompt-preview-controls.tsx`：模型、联网、语音预览按钮及不可用提示。
- 创建 `web-react/src/components/assistant-ui/suggestions.tsx`：快捷建议词与填充输入框行为。
- 创建 `web-react/src/components/assistant-ui/sources-group.tsx`：消息级来源计数与安全链接折叠区。
- 创建 `web-react/src/components/assistant-ui/streaming-cursor.tsx`：仅在助手消息运行时显示的流式光标。
- 创建对应 `*.test.tsx`：为每个新增组件提供独立行为测试。
- 修改 `web-react/src/components/assistant-ui/thread.tsx`：按 Conversation、Message 和 PromptInput 结构组合组件。
- 修改 `web-react/src/components/assistant-ui/reasoning.tsx`：对齐示例的默认折叠触发器和状态文案。
- 修改 `web-react/src/components/assistant-ui/tool-group.tsx`：对齐示例工具框的摘要、展开层级和终端结果。
- 修改 `web-react/src/components/assistant-ui/tool-fallback.tsx`：保持审批独立并路由聚合工具。
- 修改 `web-react/src/lib/irisRuntime.ts`：聚合来源和普通工具，保持审批部件独立。
- 修改 `web-react/src/App.css`：实现用户确认 Demo 的完整聊天样式和响应式规则。
- 修改现有布局、运行时和输入法测试，覆盖整合后的真实数据流。

### 任务 1：建立消息级来源聚合

**文件：**
- 创建：`web-react/src/components/assistant-ui/sources-group.tsx`
- 创建：`web-react/src/components/assistant-ui/sources-group.test.tsx`
- 修改：`web-react/src/lib/irisRuntime.ts`
- 修改：`web-react/src/lib/irisRuntime.parts.test.ts`
- 修改：`web-react/src/components/assistant-ui/tool-fallback.tsx`

- [ ] **步骤 1：编写失败的来源聚合测试**

在 `irisRuntime.parts.test.ts` 增加：

```ts
it("groups URL sources into one synthetic part", () => {
  const parts = groupSourceParts([
    { type: "source", sourceType: "url", id: "1", url: "https://react.dev", title: "React" },
    { type: "source", sourceType: "url", id: "2", url: "https://vite.dev", title: "Vite" },
  ]);
  expect(parts).toMatchObject([{
    type: "tool-call",
    toolName: "iris_sources_group",
    result: { __irisKind: "sources-group", items: [{ title: "React" }, { title: "Vite" }] },
  }]);
});
```

在 `sources-group.test.tsx` 增加：

```tsx
render(<SourcesGroup items={[
  { id: "1", url: "https://react.dev", title: "React" },
  { id: "2", url: "javascript:alert(1)", title: "Unsafe" },
]} />);
const trigger = screen.getByRole("button", { name: "共 2 个来源" });
expect(trigger).toHaveAttribute("aria-expanded", "false");
await user.click(trigger);
expect(screen.getByRole("link", { name: /React/ })).toBeVisible();
expect(screen.queryByRole("link", { name: /Unsafe/ })).not.toBeInTheDocument();
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/lib/irisRuntime.parts.test.ts src/components/assistant-ui/sources-group.test.tsx`

预期：FAIL，`groupSourceParts` 和 `SourcesGroup` 尚不存在。

- [ ] **步骤 3：实现聚合类型和安全来源组件**

在 `irisRuntime.ts` 导出：

```ts
export type IrisSourcesGroupResult = {
  __irisKind: "sources-group";
  items: Array<{ id: string; url: string; title?: string }>;
};

export function groupSourceParts(parts: ThreadAssistantMessagePart[]): ThreadAssistantMessagePart[] {
  const sources = parts.filter((part) => part.type === "source");
  const rest = parts.filter((part) => part.type !== "source");
  if (!sources.length) return rest;
  return [{
    type: "tool-call",
    toolCallId: "iris-sources-group",
    toolName: "iris_sources_group",
    args: {},
    argsText: "{}",
    result: { __irisKind: "sources-group", items: sources.map(({ id, url, title }) => ({ id, url, title })) },
  } as unknown as ThreadAssistantMessagePart, ...rest];
}
```

`SourcesGroup` 使用 `new URL()`，仅允许 `http:` 和 `https:`；触发器默认 `aria-expanded="false"`。在 `tool-fallback.tsx` 中优先识别 `sources-group` 并渲染该组件。

- [ ] **步骤 4：运行聚焦测试验证通过**

运行：`npm test -- --run src/lib/irisRuntime.parts.test.ts src/components/assistant-ui/sources-group.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交（仅 Git 可用时）**

```bash
git add web-react/src/lib/irisRuntime.ts web-react/src/lib/irisRuntime.parts.test.ts web-react/src/components/assistant-ui/sources-group.tsx web-react/src/components/assistant-ui/sources-group.test.tsx web-react/src/components/assistant-ui/tool-fallback.tsx
git commit -m "feat: group assistant message sources"
```

### 任务 2：实现示例式流式消息与推理折叠

**文件：**
- 创建：`web-react/src/components/assistant-ui/streaming-cursor.tsx`
- 创建：`web-react/src/components/assistant-ui/streaming-cursor.test.tsx`
- 修改：`web-react/src/components/assistant-ui/reasoning.tsx`
- 创建：`web-react/src/components/assistant-ui/reasoning.test.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`

- [ ] **步骤 1：编写失败的流式和推理测试**

```tsx
it("shows the cursor only while streaming", () => {
  const { rerender } = render(<StreamingCursor running />);
  expect(screen.getByLabelText("正在生成")).toBeVisible();
  rerender(<StreamingCursor running={false} />);
  expect(screen.queryByLabelText("正在生成")).not.toBeInTheDocument();
});

it("keeps reasoning collapsed by default", async () => {
  render(<Reasoning text="分析项目结构" status={{ type: "complete" }} />);
  const trigger = screen.getByRole("button", { name: "思考过程" });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await user.click(trigger);
  expect(screen.getByText("分析项目结构")).toBeVisible();
});
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/components/assistant-ui/streaming-cursor.test.tsx src/components/assistant-ui/reasoning.test.tsx`

预期：FAIL，流式光标组件缺失，推理组件测试接口不匹配或折叠语义不完整。

- [ ] **步骤 3：实现最小组件并接入助手消息**

```tsx
export function StreamingCursor({ running }: { running: boolean }) {
  return running ? <span className="iris-streaming-cursor" aria-label="正在生成" /> : null;
}
```

`Reasoning` 默认 `open=false`，运行文案为“正在思考”，完成文案为“思考过程”。在 `AssistantMessage` 的正文部件之后用 `AssistantIf condition={({ thread }) => thread.isRunning}` 渲染 `<StreamingCursor running />`，并在错误或完成状态中不渲染。

- [ ] **步骤 4：运行聚焦测试和输入法回归测试**

运行：`npm test -- --run src/components/assistant-ui/streaming-cursor.test.tsx src/components/assistant-ui/reasoning.test.tsx src/components/AssistantChat.composition.test.tsx`

预期：PASS；中文组合输入测试继续通过。

- [ ] **步骤 5：提交（仅 Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/streaming-cursor.tsx web-react/src/components/assistant-ui/streaming-cursor.test.tsx web-react/src/components/assistant-ui/reasoning.tsx web-react/src/components/assistant-ui/reasoning.test.tsx web-react/src/components/assistant-ui/thread.tsx
git commit -m "feat: add AI Elements streaming message states"
```

### 任务 3：重构 PromptInput 与预览控件

**文件：**
- 创建：`web-react/src/components/assistant-ui/prompt-preview-controls.tsx`
- 创建：`web-react/src/components/assistant-ui/prompt-preview-controls.test.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`
- 修改：`web-react/src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 1：编写失败的输入区结构测试**

```tsx
expect(container.querySelector(".iris-prompt-header")).toBeInTheDocument();
expect(container.querySelector(".iris-prompt-body")).toBeInTheDocument();
expect(container.querySelector(".iris-prompt-footer")).toBeInTheDocument();
expect(screen.getByRole("button", { name: "语音输入（暂未开放）" })).toBeVisible();
expect(screen.getByRole("button", { name: "联网搜索（暂未开放）" })).toBeVisible();
expect(screen.getByRole("button", { name: "选择模型（暂未开放）" })).toBeVisible();
```

在预览控件测试中点击每个按钮并断言同一 `role="status"` 区域显示“暂未开放”，且传入的 `onPreviewAction` 只收到控件名称，不调用发送回调。

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/components/assistant-ui/prompt-preview-controls.test.tsx src/components/AssistantChat.composition.test.tsx`

预期：FAIL，三段结构和预览控件不存在。

- [ ] **步骤 3：实现 PromptInput 三段结构**

在 `thread.tsx` 中把 Composer 改为：

```tsx
<ComposerPrimitive.Root className="iris-prompt-input">
  <ComposerPrimitive.AttachmentDropzone className="iris-prompt-dropzone">
    <div className="iris-prompt-header"><ComposerAttachments /></div>
    <div className="iris-prompt-body"><ImeSafeComposerInput /></div>
    <div className="iris-prompt-footer">
      <div className="iris-prompt-tools"><ComposerAddAttachment /><PromptPreviewControls /></div>
      <ComposerAction />
    </div>
  </ComposerPrimitive.AttachmentDropzone>
</ComposerPrimitive.Root>
```

`PromptPreviewControls` 渲染 Mic、Globe、Sparkles/ChevronDown 三个按钮；点击只更新本地 `notice`，通过 `role="status"` 呈现“语音输入暂未开放”等文案。

- [ ] **步骤 4：保留 IME 和发送状态行为**

不得替换 `ImeSafeComposerInput` 的 `draft`、`composingRef`、`onCompositionStart` 和 `onCompositionEnd`。非运行状态使用 `ComposerPrimitive.Send`，运行状态使用 `ComposerPrimitive.Cancel`；发送按钮保持 `aria-label="发送消息"`，停止按钮保持 `aria-label="停止生成"`。

- [ ] **步骤 5：运行输入区测试验证通过**

运行：`npm test -- --run src/components/assistant-ui/prompt-preview-controls.test.tsx src/components/AssistantChat.composition.test.tsx`

预期：PASS。

- [ ] **步骤 6：提交（仅 Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/prompt-preview-controls.tsx web-react/src/components/assistant-ui/prompt-preview-controls.test.tsx web-react/src/components/assistant-ui/thread.tsx web-react/src/components/AssistantChat.composition.test.tsx
git commit -m "feat: rebuild AI Elements prompt input"
```

### 任务 4：实现快捷建议词

**文件：**
- 创建：`web-react/src/components/assistant-ui/suggestions.tsx`
- 创建：`web-react/src/components/assistant-ui/suggestions.test.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`

- [ ] **步骤 1：编写失败的建议词测试**

```tsx
render(<Suggestions items={["分析项目", "运行测试"]} onSelect={onSelect} />);
await user.click(screen.getByRole("button", { name: "分析项目" }));
expect(onSelect).toHaveBeenCalledWith("分析项目");
```

在线程集成测试中点击建议词后断言 `消息输入框` 的值变为建议文本，但发送回调未调用。

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/components/assistant-ui/suggestions.test.tsx src/components/AssistantChat.composition.test.tsx`

预期：FAIL，`Suggestions` 不存在。

- [ ] **步骤 3：实现建议词并接入运行时草稿**

`Suggestions` 接收 `items` 和 `onSelect`，使用普通 `button type="button"`。在线程包装组件中通过 `useComposerRuntime().setText(value)` 填入草稿，不触发 `send()`。默认建议为“分析这个项目”“帮我定位问题”“运行项目测试”。

- [ ] **步骤 4：运行聚焦测试验证通过**

运行：`npm test -- --run src/components/assistant-ui/suggestions.test.tsx src/components/AssistantChat.composition.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交（仅 Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/suggestions.tsx web-react/src/components/assistant-ui/suggestions.test.tsx web-react/src/components/assistant-ui/thread.tsx
git commit -m "feat: add chat prompt suggestions"
```

### 任务 5：完善 AI Elements 工具框

**文件：**
- 修改：`web-react/src/components/assistant-ui/tool-group.tsx`
- 修改：`web-react/src/components/assistant-ui/tool-group.test.tsx`
- 修改：`web-react/src/components/assistant-ui/tool-fallback.tsx`
- 修改：`web-react/src/lib/irisRuntime.ts`
- 修改：`web-react/src/lib/irisRuntime.parts.test.ts`

- [ ] **步骤 1：扩展失败测试覆盖状态与审批分离**

```tsx
expect(screen.getByRole("button", { name: "正在执行 2 个工具" })).toHaveAttribute("aria-expanded", "false");
expect(screen.getByRole("button", { name: "1 个工具执行失败" })).toBeVisible();
```

运行时测试继续断言审批结果 `__irisKind: "approval"` 不出现在 `IrisToolGroupResult.items` 中。

- [ ] **步骤 2：运行测试并确认缺少失败摘要或终端详情**

运行：`npm test -- --run src/components/assistant-ui/tool-group.test.tsx src/lib/irisRuntime.parts.test.ts`

预期：至少一个新状态或终端详情断言 FAIL。

- [ ] **步骤 3：实现工具摘要和逐项详情**

摘要优先级为运行中、失败、完成。组窗口默认关闭；展开后每个工具使用 `<details>`，参数和普通结果渲染为安全 JSON。终端类结果包含 `stdout`、`stderr` 或 `command` 时，在该详情中复用现有 `Terminal` 组件。审批判断保持在聚合路由之外。

- [ ] **步骤 4：运行工具回归测试**

运行：`npm test -- --run src/components/assistant-ui/tool-group.test.tsx src/lib/irisRuntime.parts.test.ts tests/ThreadRichParts.theme.test.ts`

预期：PASS。

- [ ] **步骤 5：提交（仅 Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/tool-group.tsx web-react/src/components/assistant-ui/tool-group.test.tsx web-react/src/components/assistant-ui/tool-fallback.tsx web-react/src/lib/irisRuntime.ts web-react/src/lib/irisRuntime.parts.test.ts
git commit -m "feat: refine AI Elements tool group"
```

### 任务 6：应用已确认 Demo 的视觉与响应式规则

**文件：**
- 修改：`web-react/src/App.css`
- 修改：`web-react/tests/ChatLayout.theme.test.ts`
- 修改：`web-react/tests/ThreadRichParts.theme.test.ts`
- 修改：`web-react/src/App.test.tsx`

- [ ] **步骤 1：编写失败的主题契约测试**

```ts
expect(css).toContain(".iris-prompt-header");
expect(css).toContain(".iris-prompt-footer");
expect(css).toContain(".iris-streaming-cursor");
expect(css).toContain(".iris-suggestions");
expect(css).toContain("@media (max-width: 720px)");
```

- [ ] **步骤 2：运行主题测试验证失败**

运行：`npm test -- --run tests/ChatLayout.theme.test.ts tests/ThreadRichParts.theme.test.ts src/App.test.tsx`

预期：FAIL，缺少新组件样式契约。

- [ ] **步骤 3：实现确认版视觉**

在 `App.css` 末尾添加作用域规则：消息列最大宽度 `48rem`；用户气泡右对齐；助手正文无外层卡片；PromptInput 使用 `16px` 圆角、细边框和轻阴影；Header/Body/Footer 分区；工具组使用单层边框；光标使用 `@keyframes iris-cursor-blink`；建议词为横向可换行的小按钮。所有颜色只使用现有 `--background`、`--foreground`、`--muted`、`--muted-foreground`、`--border` 和 `--ring` 主题变量。

- [ ] **步骤 4：实现窄屏规则**

在 `max-width: 720px` 下隐藏 `.iris-suggestions`，隐藏模型名称但保留模型图标，聊天左右内边距改为 `12px`，PromptInput 宽度为 `100%`，用户气泡最大宽度为 `88%`，侧栏继续使用现有覆盖层行为。

- [ ] **步骤 5：运行主题和组件测试**

运行：`npm test -- --run tests/ChatLayout.theme.test.ts tests/ThreadRichParts.theme.test.ts src/App.test.tsx src/components/AssistantChat.composition.test.tsx`

预期：PASS。

- [ ] **步骤 6：提交（仅 Git 可用时）**

```bash
git add web-react/src/App.css web-react/tests/ChatLayout.theme.test.ts web-react/tests/ThreadRichParts.theme.test.ts web-react/src/App.test.tsx web-react/src/components/AssistantChat.composition.test.tsx
git commit -m "style: match approved AI Elements chat demo"
```

### 任务 7：完整回归与浏览器验收

**文件：**
- 验证：`web-react/src/**`
- 验证：`web-react/tests/**`

- [ ] **步骤 1：运行全部测试**

运行：`npm test -- --run`

预期：全部测试 PASS，0 failed。

- [ ] **步骤 2：运行生产构建**

运行：`npm run build`

预期：退出码 0；允许已有的大 chunk 提示。

- [ ] **步骤 3：运行静态检查**

运行：`npm run lint`

预期：退出码 0；不得新增本次文件的警告。现存 `only-export-components` 和 `store-shim.js` 未使用导入警告记录为既有问题。

- [ ] **步骤 4：桌面浏览器验收**

刷新 `http://localhost:5173/`，检查消息排版、流式光标、思考折叠、来源计数、单一工具聚合窗和 PromptInput 三段结构。输入“中文测试 123”，等待一秒确认内容保持，然后清空，不发送消息。

- [ ] **步骤 5：窄屏浏览器验收**

使用 390×844 viewport 检查侧栏默认隐藏、消息无水平溢出、预览控件合理收缩、附件和发送按钮可见；完成后恢复 viewport。

- [ ] **步骤 6：副作用安全检查**

确认验收过程未提交聊天消息、未批准或拒绝工具、未上传附件、未触发模型/联网/语音网络请求，并检查浏览器控制台无新增错误。

## 完成标准

- AI Elements 对应的 Conversation、Message、Reasoning、Sources、ToolGroup、PromptInput 和 Suggestions 均有真实组件边界与测试。
- 现有 Iris 流式输出、会话、附件、工具审批和中文输入法行为保持可用。
- 模型、联网和语音控件清晰标注暂未开放，且不改变请求数据。
- 全部测试、生产构建和 Lint 以退出码 0 完成。
- 桌面与 390px 窄屏浏览器验收通过，控制台无新增错误。
