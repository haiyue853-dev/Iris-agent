import ReportHistory from './ReportHistory';
import ReportPreview from './ReportPreview';
import ReportSourceEditor from './ReportSourceEditor';
import AttachmentQueue from './AttachmentQueue';
import ReportChat from './ReportChat';
import ReportMessageList from './ReportMessageList';
import ReportSuggestionCard from './ReportSuggestionCard';
import ReportWorkspace from './ReportWorkspace';
import { useDailyReports } from '../../hooks/useDailyReports';
import { useReportWorkspace } from '../../hooks/useReportWorkspace';

export default function DailyReportPage({ currentSessionId }: { currentSessionId: string }) {
  const reports = useDailyReports({ currentSessionId });
  const workspace = useReportWorkspace({
    report: reports.report,
    onReportUpdated: reports.applyExternalReport,
    onError: reports.setExternalError,
  });
  const reportsBusy = reports.busyAction !== null;
  const workspaceDisabled = reportsBusy || workspace.busy || !workspace.ready;

  return <div className="daily-report-page">
    <ReportWorkspace
      activeMobilePane={reports.activeMobilePane}
      onPaneChange={reports.setActiveMobilePane}
      error={reports.error}
      previewJumpKey={reports.previewJumpKey}
      history={<ReportHistory
        reports={reports.reports}
        selectedDate={reports.selectedDate}
        report={reports.report}
        busy={reportsBusy}
        onSelect={reports.selectDate}
        onRestore={reports.restore}
      />}
      source={<div className="report-chat-pane">
        <ReportSourceEditor
          selectedDate={reports.selectedDate}
          notes={reports.sourceNotes}
          includeChat={reports.includeChat}
          hasCurrentSession={Boolean(currentSessionId)}
          generating={reports.busyAction === 'generate'}
          disabled={reportsBusy}
          onDateChange={reports.selectDate}
          onNotesChange={reports.setSourceNotes}
          onIncludeChatChange={reports.setIncludeChat}
          onGenerate={reports.generate}
        />
        <AttachmentQueue
          attachments={workspace.attachments}
          selectedIds={workspace.selectedIds}
          busy={workspaceDisabled}
          onUpload={workspace.upload}
          onToggle={workspace.toggleAttachment}
          onRemove={workspace.remove}
        />
        <ReportMessageList messages={workspace.messages} />
        <ReportChat disabled={workspaceDisabled} onSend={workspace.send} />
        <ReportSuggestionCard suggestion={workspace.suggestion} busy={reportsBusy || workspace.busy} onApply={workspace.apply} />
      </div>}
      preview={<ReportPreview
        hasReport={Boolean(reports.report)}
        sections={reports.draftSections}
        saveState={reports.saveState}
        busyAction={reports.busyAction}
        downloadUrl={reports.downloadUrl}
        onUpdate={reports.updateSection}
        onRetrySave={reports.retrySave}
        onCopy={reports.copyMarkdown}
        onRevise={reports.revise}
      />}
    />
  </div>;
}
