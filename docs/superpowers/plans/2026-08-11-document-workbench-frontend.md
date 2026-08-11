# 文档工作台前端实现计划

> **面向 AI 代理的工作者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把文档工作台占位页交付为可上传资料、生成、编辑、保存并导出草稿的响应式前端。

**架构：** 以 `useDocumentWorkbench` 集中维护 API 调用和编辑状态；四个专注组件分别展示工作区、资料库、生成器与编辑器。沿用日报工作台的三栏/移动标签模式，后端接口保持不变。

**技术栈：** React 19、TypeScript、Vite、Vitest、Testing Library、既有 FastAPI 文档 API。

---

## 文件结构

- 新建 `web-react/src/api/documents.ts`：文档 API、错误类型和导出 URL。
- 修改 `web-react/src/types.ts`：文档与草稿的 API 类型。
- 新建 `web-react/src/hooks/useDocumentWorkbench.ts`：加载、上传、选择、生成、编辑、保存、冲突恢复状态。
- 新建 `web-react/src/components/documents/DocumentLibrary.tsx`：资料上传、状态、选择和删除。
- 新建 `web-react/src/components/documents/DocumentComposer.tsx`：模板、指令、生成与草稿列表。
- 新建 `web-react/src/components/documents/DocumentEditor.tsx`：草稿编辑、保存、冲突恢复与导出。
- 新建 `web-react/src/components/documents/DocumentWorkbenchPage.tsx`：桌面三栏和移动端标签的组合。
- 修改 `web-react/src/App.tsx`：用工作台页替换 documents 占位页，并补充主区域语义标签。
- 修改 `web-react/src/App.css`：工作台卡片、状态和响应式布局。
- 新建 `web-react/src/api/documents.test.ts`：客户端请求和错误映射。
- 新建 `web-react/src/hooks/useDocumentWorkbench.test.tsx`：状态流、生成、保存与冲突。
- 新建 `web-react/src/components/documents/DocumentWorkbenchPage.test.tsx`：工作台交互与移动标签。
- 修改 `web-react/src/App.test.tsx`：侧栏导航进入工作台。

### 任务 1：定义文档客户端和类型

**文件：**
- 创建：`web-react/src/api/documents.ts`
- 修改：`web-react/src/types.ts`
- 测试：`web-react/src/api/documents.test.ts`

- [ ] **步骤 1：编写失败的 API 客户端测试**

```ts
it('uploads a document as multipart form data', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(document)));
  await uploadDocument(new File(['brief'], 'brief.md', { type: 'text/markdown' }));
  expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/documents', expect.objectContaining({ method: 'POST' }));
});

it('throws a document API error with the server error code', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errorResponse(409, 'document_revision_conflict', '草稿版本已变化')));
  await expect(saveDocumentDraft('draft-1', '标题', '# 内容', 1)).rejects.toMatchObject({ code: 'document_revision_conflict', status: 409 });
});
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`npm run test -- src/api/documents.test.ts`

预期：FAIL，提示找不到 `./documents` 模块或导出函数。

- [ ] **步骤 3：实现最小 API 和类型定义**

```ts
export type DocumentTemplate = 'meeting_minutes' | 'prd' | 'technical_solution' | 'weekly_report';

export async function saveDocumentDraft(id: string, title: string, markdown: string, expectedRevision: number) {
  return requestJson<DocumentDraft>(`/api/documents/drafts/${encodeURIComponent(id)}`, jsonRequest('PUT', {
    title, markdown, expected_revision: expectedRevision,
  }));
}
```

实现 `listDocuments`、`uploadDocument`、`deleteDocument`、`listDocumentDrafts`、`getDocumentDraft`、`generateDocumentDraft`、`saveDocumentDraft` 和 `documentDraftExportUrl`；用 `DocumentApiError` 保留 `code` 与 `status`。

- [ ] **步骤 4：运行 API 测试并确认通过**

运行：`npm run test -- src/api/documents.test.ts`

预期：PASS。

- [ ] **步骤 5：提交 API 基础层**

```bash
git add web-react/src/api/documents.ts web-react/src/api/documents.test.ts web-react/src/types.ts
git commit -m "feat: add document workbench API client"
```

### 任务 2：实现可测试的工作台状态 Hook

**文件：**
- 创建：`web-react/src/hooks/useDocumentWorkbench.ts`
- 测试：`web-react/src/hooks/useDocumentWorkbench.test.tsx`

- [ ] **步骤 1：编写失败的状态流测试**

```tsx
it('generates from ready selected documents and opens the new draft', async () => {
  vi.mocked(listDocuments).mockResolvedValue([readyDocument, pendingDocument]);
  vi.mocked(generateDocumentDraft).mockResolvedValue(generatedDraft);
  const { result } = renderHook(() => useDocumentWorkbench());
  await waitFor(() => result.current.ready);
  act(() => result.current.toggleDocument(readyDocument.id));
  await act(() => result.current.generate());
  expect(generateDocumentDraft).toHaveBeenCalledWith('prd', [readyDocument.id], '');
  expect(result.current.draft?.id).toBe(generatedDraft.id);
});

it('retains local edits when save reports a revision conflict', async () => {
  vi.mocked(saveDocumentDraft).mockRejectedValue(new DocumentApiError('document_revision_conflict', '冲突', 409));
  // 修改标题和正文后保存
  expect(result.current.saveState).toBe('conflict');
  expect(result.current.markdown).toBe('# 本地内容');
});
```

- [ ] **步骤 2：运行 Hook 测试并确认失败**

运行：`npm run test -- src/hooks/useDocumentWorkbench.test.tsx`

预期：FAIL，提示 Hook 尚不存在。

- [ ] **步骤 3：实现 Hook 的状态和操作**

```ts
const toggleDocument = useCallback((id: string) => {
  if (documents.find((item) => item.id === id)?.extraction_status !== 'ready') return;
  setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
}, [documents]);

const save = useCallback(async () => {
  if (!draftRef.current || busyRef.current) return;
  setSaveState('saving');
  try { applyDraft(await saveDocumentDraft(draft.id, title.trim(), markdown.trim(), draft.revision)); }
  catch (error) { setSaveState(error instanceof DocumentApiError && error.status === 409 ? 'conflict' : 'error'); }
}, [applyDraft, markdown, title]);
```

加载资料和草稿；上传后追加/刷新资料；删除时取消选择；仅允许 `ready` 资料参与生成；生成成功加载新草稿；保存成功替换版本；冲突保留本地字段，`reloadDraft` 从服务端覆盖；操作期间维护 `busy`、`error` 和 `ready`。

- [ ] **步骤 4：运行 Hook 测试并确认通过**

运行：`npm run test -- src/hooks/useDocumentWorkbench.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交工作台状态层**

```bash
git add web-react/src/hooks/useDocumentWorkbench.ts web-react/src/hooks/useDocumentWorkbench.test.tsx
git commit -m "feat: manage document workbench state"
```

### 任务 3：构建资料、生成与编辑组件

**文件：**
- 创建：`web-react/src/components/documents/DocumentLibrary.tsx`
- 创建：`web-react/src/components/documents/DocumentComposer.tsx`
- 创建：`web-react/src/components/documents/DocumentEditor.tsx`
- 创建：`web-react/src/components/documents/DocumentWorkbenchPage.tsx`
- 测试：`web-react/src/components/documents/DocumentWorkbenchPage.test.tsx`

- [ ] **步骤 1：编写失败的组件交互测试**

```tsx
it('disables a pending document but allows a ready document to be selected', async () => {
  render(<DocumentWorkbenchPage />);
  await user.click(screen.getByRole('checkbox', { name: /ready\.md/i }));
  expect(screen.getByRole('checkbox', { name: /pending\.pdf/i })).toBeDisabled();
});

it('switches to the editor pane after a successful generation', async () => {
  render(<DocumentWorkbenchPage />);
  await user.click(screen.getByRole('button', { name: '生成草稿' }));
  expect(screen.getByRole('tabpanel', { name: '编辑' })).toBeVisible();
});
```

- [ ] **步骤 2：运行组件测试并确认失败**

运行：`npm run test -- src/components/documents/DocumentWorkbenchPage.test.tsx`

预期：FAIL，提示组件尚不存在。

- [ ] **步骤 3：实现组件和可访问性语义**

```tsx
<button type="button" onClick={() => void onGenerate()} disabled={busy || selectedIds.length === 0}>
  {busy ? '正在生成…' : '生成草稿'}
</button>

<a href={documentDraftExportUrl(draft.id, 'docx')}>导出 Word</a>
```

资料项使用具名复选框和解析状态；上传 input 接受 `.txt,.md,.docx,.pdf,.xlsx,.xls`；编辑区使用 `<input>` 和 `<textarea>`，明确保存状态和冲突恢复按钮；页面使用 `role="tabpanel"` 和具名移动端标签，桌面端同时显示三栏。

- [ ] **步骤 4：运行组件测试并确认通过**

运行：`npm run test -- src/components/documents/DocumentWorkbenchPage.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交工作台组件**

```bash
git add web-react/src/components/documents
git commit -m "feat: add document workbench interface"
```

### 任务 4：接入 App、样式并做回归验证

**文件：**
- 修改：`web-react/src/App.tsx`
- 修改：`web-react/src/App.css`
- 修改：`web-react/src/App.test.tsx`

- [ ] **步骤 1：编写失败的导航测试**

```tsx
it('opens the document workbench from the left sidebar', async () => {
  render(<App />);
  await userEvent.setup().click(screen.getByRole('button', { name: '文档工作台' }));
  expect(screen.getByRole('main', { name: '文档工作台' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '文档工作台' })).toBeInTheDocument();
});
```

- [ ] **步骤 2：运行 App 测试并确认失败**

运行：`npm run test -- src/App.test.tsx`

预期：FAIL，仍显示“即将上线”的占位文本。

- [ ] **步骤 3：替换占位页并添加响应式样式**

```tsx
} : activeView === 'documents' ? (
  <DocumentWorkbenchPage />
) : activeView === 'radar' ? (
```

将 `main` 的 `aria-label` 扩展为 documents；添加 `.document-workbench` 三栏网格、资料状态色、编辑区和 `max-width: 960px` 下的标签布局。复用现有主题变量，不新增依赖。

- [ ] **步骤 4：运行前端回归测试和构建**

运行：`npm run test && npm run build`

预期：全部 PASS，构建完成；允许既有 Mermaid 大包提示。

- [ ] **步骤 5：运行后端回归与最终提交**

运行：`..\.venv\Scripts\python.exe -m pytest`

预期：全部已有 Python 测试通过。

```bash
git add web-react/src/App.tsx web-react/src/App.css web-react/src/App.test.tsx
git commit -m "feat: launch document workbench"
```
