import type { WorkbenchDocument } from '../../types';

type Props = {
  documents: WorkbenchDocument[];
  selectedIds: string[];
  busy: boolean;
  onToggle: (id: string) => void;
  onUpload: (files: File[]) => void;
  onRemove: (id: string) => void;
};

const statusLabel = (document: WorkbenchDocument) => {
  if (document.extraction_status === 'ready') return document.text_truncated ? '已解析（内容已截断）' : '已解析';
  if (document.extraction_status === 'failed') return document.extraction_message || '解析失败';
  return '正在解析';
};

export default function DocumentLibrary({ documents, selectedIds, busy, onToggle, onUpload, onRemove }: Props) {
  return <section className="document-pane document-library" aria-label="资料库">
    <div className="document-pane-heading"><h2>资料库</h2><span>{selectedIds.length} 已选</span></div>
    <label className="document-upload">
      <span>上传资料</span>
      <input aria-label="上传资料" type="file" multiple accept=".txt,.md,.docx,.pdf,.xlsx,.xls" disabled={busy}
        onChange={(event) => { void onUpload(Array.from(event.target.files || [])); event.target.value = ''; }} />
    </label>
    <p className="document-hint">支持 TXT、Markdown、Word、PDF 和 Excel，单文件最大 10MB。</p>
    <div className="document-list">
      {documents.length === 0 ? <p className="document-empty">还没有资料，先上传文件开始吧。</p> : documents.map((document) => {
        const selectable = document.extraction_status === 'ready';
        return <article className="document-item" key={document.id}>
          <label>
            <input type="checkbox" aria-label={document.original_name} checked={selectedIds.includes(document.id)} disabled={!selectable || busy}
              onChange={() => onToggle(document.id)} />
            <span className="document-name">{document.original_name}</span>
          </label>
          <p className={`document-status ${document.extraction_status}`}>{statusLabel(document)}</p>
          <button type="button" className="document-delete" disabled={busy} onClick={() => void onRemove(document.id)}>删除</button>
        </article>;
      })}
    </div>
  </section>;
}
