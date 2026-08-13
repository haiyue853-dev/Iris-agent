# Draw.io 独占 UML 工作台实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 逐项执行本计划；每项完成后运行指定验证，并在提交前完成完整前端验证。

**目标：** 移除不可达的 React Flow UML 画布，将 UML 工作台收敛为 Draw.io 唯一编辑器，同时保留 AI 生成 Mermaid、手动重新导入、保存和导出能力。

**架构：** `UmlFlowPage` 只维护需求、图表类型、Mermaid 源码及 Draw.io 导入请求。`DrawioEditor` 继续独立处理 iframe、持久化及 PNG/SVG/XML 导出。旧 React Flow 文件、样式、存储逻辑及依赖整体移除，浏览器的 `iris_uml_board_v1` 不读取也不删除。

**技术栈：** React 19、TypeScript、Vitest、Testing Library、Vite、Draw.io embed API。

## 文件边界

修改：

- `web-react/src/components/uml/UmlFlowPage.tsx`：Draw.io 专用页面编排。
- `web-react/src/components/uml/UmlFlowPage.test.tsx`：生成自动导入与手动重新导入测试。
- `web-react/src/App.css`：移除旧画布样式，保留专业画布仍使用的通用样式。
- `web-react/package.json`、`web-react/package-lock.json`：移除废弃依赖。
- `PROJECT_STATUS.md`：记录最终状态。

删除：

- `web-react/src/components/uml/ContextMenu.tsx`
- `web-react/src/components/uml/exportDiagram.ts`
- `web-react/src/components/uml/FlowCanvas.tsx`
- `web-react/src/components/uml/FlowEdge.tsx`
- `web-react/src/components/uml/FlowImageNode.tsx`
- `web-react/src/components/uml/FlowNode.tsx`
- `web-react/src/components/uml/mermaidParser.ts`
- `web-react/src/components/uml/PropertiesPanel.tsx`
- `web-react/src/components/uml/ShapePalette.tsx`

保留：`DrawioEditor.tsx`、`DrawioEditor.test.tsx`、`drawioStorage.ts`。不触及未跟踪文件与目录，包括 `web-react/src/tmp_c.py`。

## 任务 1：锁定 Draw.io 页面契约

**文件：** `web-react/src/components/uml/UmlFlowPage.test.tsx`、`web-react/src/components/uml/UmlFlowPage.tsx`

- [ ] **步骤 1：先增加失败测试。** 在既有 `DrawioEditor` mock 属性采集基础上，新增“编辑 Mermaid 后点击重新导入”用例；断言 `importRequest` 从 `0` 变为正数，并传入编辑后的 Mermaid。

```tsx
it('reimports edited Mermaid into Draw.io on demand', async () => {
  render(<UmlFlowPage />);
  fireEvent.change(screen.getByLabelText('Mermaid 源码'), {
    target: { value: 'flowchart TD\n A-->B' },
  });
  fireEvent.click(screen.getByRole('button', { name: '重新导入到专业画布' }));
  await waitFor(() => expect(Number(screen.getByTestId('drawio-editor').dataset.importRequest)).toBeGreaterThan(0));
});
```

- [ ] **步骤 2：运行页面测试。** 运行 `& 'C:\Program Files\nodejs\node.exe' .\node_modules\vitest\vitest.mjs run src/components/uml/UmlFlowPage.test.tsx`。预期新增测试通过，锁定必须保留的 Draw.io 交互。

- [ ] **步骤 3：收敛页面实现。** 删除所有 React Flow/Mermaid 运行时导入、`EditorMode`、`BOARD_TYPES`、旧 localStorage 读写、节点/边状态、SVG 渲染、经典画布事件及 JSX 分支。仅保留输入、图表类型、生成状态、API 错误、Mermaid 源码、Draw.io 导入请求、导入递增 ref、Draw.io 内容标记和滚动 ref。`handleGenerate` 成功后设置源码并调用 `importMermaidToProfessionalCanvas(result.mermaid)`；该函数保留原有“已有内容时确认覆盖”的保护。工具栏仅保留重新导入、复制源码、下载 `.mmd`。

- [ ] **步骤 4：运行测试并提交。** 运行 `& 'C:\Program Files\nodejs\node.exe' .\node_modules\vitest\vitest.mjs run src/components/uml/UmlFlowPage.test.tsx`，预期 3 个页面测试通过；再执行 `git add -- web-react/src/components/uml/UmlFlowPage.tsx web-react/src/components/uml/UmlFlowPage.test.tsx` 与 `git commit -m 'refactor: 收敛 UML 为 Draw.io 画布'`。

## 任务 2：删除旧模块、样式和依赖

**文件：** 上述 9 个待删除模块、`web-react/src/App.css`、`web-react/package.json`、`web-react/package-lock.json`

- [ ] **步骤 1：扫描删除前基线。** 运行 `rg -n '@xyflow/react|from .mermaid.' web-react/src web-react/package.json`。预期匹配仅在待删除模块、收敛前页面及清单内；`DrawioEditor.tsx` 只传递 Mermaid 文本协议，不直接导入包。

- [ ] **步骤 2：删除旧 React Flow 模块和样式。** 使用补丁删除 9 个旧模块。删除以“流程图可视化画板（React Flow）”开头的完整 CSS 样式段；把当前专业工作台仍使用的 `.uml-toolbar-tag` 和 `.uml-editor-textarea-short { min-height: 150px; max-height: 240px; }` 移回 UML 通用样式区。不得保留 `.react-flow__*`、`.fl-*`、`.flow-*`、`.sp-*`、`.pp-*` 选择器。

- [ ] **步骤 3：卸载废弃运行时依赖。** 在 `web-react` 目录执行 `& 'C:\Program Files\nodejs\node.exe' 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' uninstall @xyflow/react mermaid`。预期 `package.json` 与锁文件都不再列出两个包；保留与报告渲染有关的 `marked`、`@types/marked`。

- [ ] **步骤 4：验证无残留并提交。** 运行 `rg -n '@xyflow/react|from .mermaid.|React Flow|react-flow__|\.fl-|\.flow-|\.sp-|\.pp-' web-react/src web-react/package.json web-react/package-lock.json`，预期退出码为 `1`。随后执行 `git add -u -- web-react/src/components/uml web-react/src/App.css web-react/package.json web-react/package-lock.json` 及 `git commit -m 'chore: 移除 React Flow UML 旧画布'`。

## 任务 3：回归验证并记录状态

**文件：** `PROJECT_STATUS.md`

- [ ] **步骤 1：运行 UML 组件回归。** 运行 `& 'C:\Program Files\nodejs\node.exe' .\node_modules\vitest\vitest.mjs run src/components/uml/UmlFlowPage.test.tsx src/components/uml/DrawioEditor.test.tsx`。预期两个文件均通过，覆盖生成导入、手动重新导入、Draw.io 保存和 PNG/SVG/XML 导出协议。

- [ ] **步骤 2：运行完整前端验证。** 依次运行 `& 'C:\Program Files\nodejs\node.exe' .\node_modules\vitest\vitest.mjs run`、`& 'C:\Program Files\nodejs\node.exe' .\node_modules\typescript\bin\tsc -b`、`& 'C:\Program Files\nodejs\node.exe' .\node_modules\vite\bin\vite.js build`。预期全部成功；据真实输出决定是否移除 Mermaid 大 chunk 的已知限制。

- [ ] **步骤 3：更新 `PROJECT_STATUS.md`。** UML 功能说明改为 Draw.io 单一工作台；从“下一步建议”移除 React Flow 清理项，并按构建结果更新大 chunk 限制。不得修改 MCP、自动化或日报的其他状态。

- [ ] **步骤 4：最终检查并提交状态文档。** 运行 `git diff --check` 与 `git status --short`，确认无空白错误且未跟踪用户文件原样保留；然后执行 `git add -- PROJECT_STATUS.md` 与 `git commit -m 'docs: 更新 Draw.io UML 工作台状态'`。
