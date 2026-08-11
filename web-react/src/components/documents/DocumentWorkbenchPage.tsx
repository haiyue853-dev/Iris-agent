import { useDocumentWorkbench, type DocumentPane } from '../../hooks/useDocumentWorkbench';
import DocumentComposer from './DocumentComposer';
import DocumentEditor from './DocumentEditor';
import DocumentLibrary from './DocumentLibrary';

const tabs: Array<[DocumentPane, string]> = [['library', '资料'], ['compose', '生成'], ['editor', '编辑']];

export default function DocumentWorkbenchPage() {
  const workbench = useDocumentWorkbench();
  return <section className="document-workbench" aria-label="文档工作台"><header className="document-workbench-header"><h1>文档工作台</h1><p>上传本地资料，生成并持续编辑工作文档。</p></header>
    {workbench.error && <div className="document-error" role="alert">{workbench.error}</div>}
    <div className="document-mobile-tabs" role="tablist" aria-label="文档工作台区域">{tabs.map(([pane, label]) => <button type="button" key={pane} role="tab" aria-selected={workbench.mobilePane === pane} onClick={() => workbench.setMobilePane(pane)}>{label}</button>)}</div>
    <div className="document-workspace">
      <div role="tabpanel" aria-label="资料" className={workbench.mobilePane === 'library' ? 'active' : ''}><DocumentLibrary documents={workbench.documents} selectedIds={workbench.selectedIds} busy={workbench.busy} onToggle={workbench.toggleDocument} onUpload={workbench.upload} onRemove={workbench.remove} /></div>
      <div role="tabpanel" aria-label="生成" className={workbench.mobilePane === 'compose' ? 'active' : ''}><DocumentComposer template={workbench.template} instructions={workbench.instructions} selectedCount={workbench.selectedIds.length} drafts={workbench.drafts} currentDraftId={workbench.draft?.id} busy={workbench.busy} onTemplateChange={workbench.setTemplate} onInstructionsChange={workbench.setInstructions} onGenerate={workbench.generate} onOpenDraft={workbench.openDraft} /></div>
      <div role="tabpanel" aria-label="编辑" className={workbench.mobilePane === 'editor' ? 'active' : ''}><DocumentEditor draft={workbench.draft} title={workbench.title} markdown={workbench.markdown} saveState={workbench.saveState} busy={workbench.busy} onTitleChange={workbench.setTitle} onMarkdownChange={workbench.setMarkdown} onSave={workbench.save} onReload={workbench.reloadDraft} /></div>
    </div>
  </section>;
}
