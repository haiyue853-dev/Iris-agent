import type { DailyReport, ReportSummary } from '../../types';

type Props = {
  reports: ReportSummary[];
  selectedDate: string;
  report: DailyReport | null;
  busy: boolean;
  onSelect: (date: string) => void;
  onRestore: (version: number) => void;
};

const kindLabel = {
  generated: '生成',
  manual: '手动',
  ai_revision: 'AI 修改',
  restored: '恢复',
};

export default function ReportHistory({ reports, selectedDate, report, busy, onSelect, onRestore }: Props) {
  return (
    <section className="report-history">
      <header className="report-pane-header">
        <span className="report-eyebrow">日报历史</span>
        <strong>{reports.length} 份</strong>
      </header>
      <div className="report-history-list">
        {reports.length === 0 && <p className="report-empty">还没有日报，先生成今天的第一份。</p>}
        {reports.map((item) => (
          <button
            key={item.date}
            className={`report-history-item ${selectedDate === item.date ? 'active' : ''}`}
            onClick={() => onSelect(item.date)}
          >
            <strong>{item.date}</strong>
            <span>{item.summary}</span>
          </button>
        ))}
      </div>
      {report && (
        <div className="report-versions">
          <h3>修改版本</h3>
          {[...report.versions].reverse().map((version) => (
            <div className="report-version-item" key={version.number}>
              <span>v{version.number} · {kindLabel[version.kind]}</span>
              <button
                disabled={busy || version.number === report.current_version}
                onClick={() => onRestore(version.number)}
              >
                {version.number === report.current_version ? '当前' : '恢复'}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

