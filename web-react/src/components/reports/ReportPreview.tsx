import type { ReportSections } from '../../types';
import type { BusyAction, SaveState } from '../../hooks/useDailyReports';
import ReportRevisionBox from './ReportRevisionBox';

type Props = {
  hasReport: boolean;
  sections: ReportSections;
  saveState: SaveState;
  busyAction: BusyAction;
  downloadUrl: string;
  onUpdate: (key: keyof ReportSections, items: string[]) => void;
  onRetrySave: () => void;
  onCopy: () => void;
  onRevise: (instruction: string) => void;
};

const sectionLabels: Array<[keyof ReportSections, string]> = [
  ['completed', '今日完成'],
  ['in_progress', '进行中'],
  ['problems', '遇到的问题'],
  ['next_day', '明日计划'],
  ['assistance', '需要协助'],
];

const saveLabel: Record<SaveState, string> = {
  idle: '尚未生成',
  dirty: '等待保存',
  saving: '正在保存…',
  saved: '已自动保存',
  error: '保存失败',
};

export default function ReportPreview({
  hasReport,
  sections,
  saveState,
  busyAction,
  downloadUrl,
  onUpdate,
  onRetrySave,
  onCopy,
  onRevise,
}: Props) {
  const isEmptyDraft = hasReport && Object.values(sections).every((items) => items.length === 0 || items.every((item) => !item.trim()));
  return (
    <section className="report-preview">
      <header className="report-pane-header report-preview-header">
        <div>
          <span className="report-eyebrow">日报预览</span>
          <h2>汇报版日报</h2>
        </div>
        <span className={`report-save-state ${saveState}`}>{saveLabel[saveState]}</span>
      </header>
      {!hasReport ? (
        <div className="report-preview-empty">
          <strong>日报会显示在这里</strong>
          <p>填写左侧工作记录，然后生成第一版。</p>
        </div>
      ) : (
        <>
          {isEmptyDraft && <p className="report-preview-hint">日报草稿已就绪。可从工作记录、附件或对话开始，确认 AI 建议后会在这里更新。</p>}
          <div className="report-section-editors">
            {sectionLabels.map(([key, label]) => (
              <label className="report-section-editor" key={key}>
                <span>{label}</span>
                <textarea
                  aria-label={label}
                  value={sections[key].join('\n')}
                  disabled={busyAction !== null}
                  onChange={(event) => onUpdate(key, event.target.value.split('\n'))}
                />
              </label>
            ))}
          </div>
          {saveState === 'error' && (
            <button className="report-retry-button" onClick={onRetrySave}>重新保存</button>
          )}
          <div className="report-preview-actions">
            <button onClick={onCopy}>复制</button>
            <a href={downloadUrl}>下载 .md</a>
          </div>
          <ReportRevisionBox
            disabled={!hasReport || busyAction !== null}
            revising={busyAction === 'revise'}
            onRevise={onRevise}
          />
        </>
      )}
    </section>
  );
}
