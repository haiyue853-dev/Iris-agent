import ReportHistory from './ReportHistory';
import ReportPreview from './ReportPreview';
import ReportSourceEditor from './ReportSourceEditor';
import { useDailyReports, type ReportPane } from '../../hooks/useDailyReports';

export default function DailyReportPage({ currentSessionId }: { currentSessionId: string }) {
  const reports = useDailyReports({ currentSessionId });
  const panes: Array<[ReportPane, string]> = [
    ['history', '历史'],
    ['source', '记录'],
    ['preview', '预览'],
  ];

  return (
    <div className="daily-report-page">
      <div className="report-mobile-tabs" aria-label="日报页面区域">
        {panes.map(([pane, label]) => (
          <button
            key={pane}
            className={reports.activeMobilePane === pane ? 'active' : ''}
            onClick={() => reports.setActiveMobilePane(pane)}
          >
            {label}
          </button>
        ))}
      </div>
      {reports.error && <div className="report-error-banner" role="alert">{reports.error}</div>}
      <div className="report-workspace">
        <div className={`report-pane history ${reports.activeMobilePane === 'history' ? 'active' : ''}`}>
          <ReportHistory
            reports={reports.reports}
            selectedDate={reports.selectedDate}
            report={reports.report}
            busy={reports.busyAction !== null}
            onSelect={reports.selectDate}
            onRestore={reports.restore}
          />
        </div>
        <div className={`report-pane source ${reports.activeMobilePane === 'source' ? 'active' : ''}`}>
          <ReportSourceEditor
            selectedDate={reports.selectedDate}
            notes={reports.sourceNotes}
            includeChat={reports.includeChat}
            hasCurrentSession={Boolean(currentSessionId)}
            generating={reports.busyAction === 'generate'}
            onDateChange={reports.selectDate}
            onNotesChange={reports.setSourceNotes}
            onIncludeChatChange={reports.setIncludeChat}
            onGenerate={reports.generate}
          />
        </div>
        <div className={`report-pane preview ${reports.activeMobilePane === 'preview' ? 'active' : ''}`}>
          <ReportPreview
            hasReport={Boolean(reports.report)}
            sections={reports.draftSections}
            saveState={reports.saveState}
            busyAction={reports.busyAction}
            downloadUrl={reports.downloadUrl}
            onUpdate={reports.updateSection}
            onRetrySave={reports.retrySave}
            onCopy={reports.copyMarkdown}
            onRevise={reports.revise}
          />
        </div>
      </div>
    </div>
  );
}
