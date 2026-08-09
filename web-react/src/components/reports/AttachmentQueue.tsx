import { useRef, useState } from 'react';

import type { ReportAttachment } from '../../types';

type Props = {
  attachments: ReportAttachment[];
  selectedIds: string[];
  busy: boolean;
  onUpload: (files: File[], preserve: boolean) => void;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
};

const fileSize = (size: number) => (size < 1024 * 1024
  ? `${Math.max(1, Math.round(size / 1024))} KB`
  : `${(size / (1024 * 1024)).toFixed(1)} MB`);

const extractionLabel = (status?: string) => ({
  ready: '已提取',
  processing: '提取中',
  unavailable: '无法提取',
  failed: '提取失败',
}[status ?? ''] ?? '待提取');

export default function AttachmentQueue({ attachments, selectedIds, busy, onUpload, onToggle, onRemove }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [preserve, setPreserve] = useState(false);
  return <section className="attachment-queue" aria-label="日报附件">
    <div className="attachment-queue-header"><strong>参考附件</strong><label><input type="checkbox" checked={preserve} disabled={busy} onChange={(event) => setPreserve(event.target.checked)} /> 保留</label></div>
    <input ref={input} aria-label="上传附件" className="visually-hidden" type="file" multiple disabled={busy} accept=".docx,.pdf,.md,.txt,.xlsx,.xls,.png,.jpg,.jpeg,.webp" onChange={(event) => { onUpload(Array.from(event.target.files ?? []), preserve); event.currentTarget.value = ''; }} />
    <button className="report-secondary-button" disabled={busy} onClick={() => input.current?.click()}>添加文件</button>
    {attachments.length === 0 ? <p className="report-muted">可上传文档、表格、图片或文本作为日报参考。</p> : <ul className="attachment-list">{attachments.map((item) => <li key={item.id}>
      <label><input type="checkbox" checked={selectedIds.includes(item.id)} disabled={busy} onChange={() => onToggle(item.id)} /> <span>{item.original_name}</span></label>
      <small>{fileSize(item.size_bytes)} · {item.preserve ? '保留' : '临时'} · {extractionLabel(item.extraction_status)}</small>
      <button aria-label={`删除 ${item.original_name}`} disabled={busy} onClick={() => onRemove(item.id)}>×</button>
    </li>)}</ul>}
  </section>;
}

