import type { DocumentDraft, DocumentTemplate } from '../../types';

type Props = {
  template: DocumentTemplate;
  instructions: string;
  selectedCount: number;
  drafts: DocumentDraft[];
  currentDraftId?: string;
  busy: boolean;
  onTemplateChange: (template: DocumentTemplate) => void;
  onInstructionsChange: (value: string) => void;
  onGenerate: () => void;
  onOpenDraft: (id: string) => void;
};

const templates: Array<[DocumentTemplate, string]> = [
  ['meeting_minutes', '会议纪要'], ['prd', 'PRD'], ['technical_solution', '技术方案'], ['weekly_report', '周报'],
];

export default function DocumentComposer({ template, instructions, selectedCount, drafts, currentDraftId, busy, onTemplateChange, onInstructionsChange, onGenerate, onOpenDraft }: Props) {
  return <section className="document-pane document-composer" aria-label="生成草稿">
    <div className="document-pane-heading"><h2>生成草稿</h2><span>{selectedCount} 份资料</span></div>
    <label>模板<select aria-label="文档模板" value={template} disabled={busy} onChange={(event) => onTemplateChange(event.target.value as DocumentTemplate)}>
      {templates.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
    </select></label>
    <label>补充说明<textarea value={instructions} disabled={busy} placeholder="例如：面向产品与研发团队，重点说明风险" onChange={(event) => onInstructionsChange(event.target.value)} /></label>
    <button type="button" className="document-primary" disabled={busy || selectedCount === 0} onClick={() => void onGenerate()}>{busy ? '正在生成…' : '生成草稿'}</button>
    <div className="document-draft-list"><h3>草稿</h3>
      {drafts.length === 0 ? <p className="document-empty">生成的草稿会出现在这里。</p> : drafts.map((draft) => <button type="button" key={draft.id}
        className={`document-draft-item ${draft.id === currentDraftId ? 'active' : ''}`} disabled={busy} onClick={() => void onOpenDraft(draft.id)}>{draft.title}</button>)}
    </div>
  </section>;
}
