import { documentDraftExportUrl } from '../../api/documents';
import type { DocumentDraft } from '../../types';
import type { DocumentSaveState } from '../../hooks/useDocumentWorkbench';

type Props = {
  draft: DocumentDraft | null;
  title: string;
  markdown: string;
  saveState: DocumentSaveState;
  busy: boolean;
  onTitleChange: (value: string) => void;
  onMarkdownChange: (value: string) => void;
  onSave: () => void;
  onReload: () => void;
};

const saveLabel: Record<DocumentSaveState, string> = { idle: '', dirty: '未保存', saving: '正在保存…', saved: '已保存', error: '保存失败', conflict: '版本冲突' };

export default function DocumentEditor({ draft, title, markdown, saveState, busy, onTitleChange, onMarkdownChange, onSave, onReload }: Props) {
  if (!draft) return <section className="document-pane document-editor" aria-label="编辑草稿"><h2>编辑草稿</h2><p className="document-empty">选择已有草稿或生成一个新草稿后开始编辑。</p></section>;
  return <section className="document-pane document-editor" aria-label="编辑草稿">
    <div className="document-pane-heading"><h2>编辑草稿</h2><span className={`document-save-state ${saveState}`}>{saveLabel[saveState]}</span></div>
    <label>标题<input aria-label="草稿标题" value={title} disabled={busy} onChange={(event) => onTitleChange(event.target.value)} /></label>
    <label className="document-markdown-label">Markdown 正文<textarea aria-label="Markdown 正文" value={markdown} disabled={busy} onChange={(event) => onMarkdownChange(event.target.value)} /></label>
    {saveState === 'conflict' && <div className="document-conflict" role="alert">草稿已被其他修改更新。重新加载会覆盖本地内容。<button type="button" disabled={busy} onClick={() => void onReload()}>重新加载最新版本</button></div>}
    <div className="document-editor-actions"><button type="button" className="document-primary" disabled={busy || !title.trim() || !markdown.trim()} onClick={() => void onSave()}>{saveState === 'saving' ? '正在保存…' : '保存草稿'}</button>
      <a href={documentDraftExportUrl(draft.id, 'markdown')}>导出 Markdown</a><a href={documentDraftExportUrl(draft.id, 'docx')}>导出 Word</a>
    </div>
  </section>;
}
