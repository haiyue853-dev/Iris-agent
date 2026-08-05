type Props = {
  selectedDate: string;
  notes: string;
  includeChat: boolean;
  hasCurrentSession: boolean;
  generating: boolean;
  onDateChange: (date: string) => void;
  onNotesChange: (value: string) => void;
  onIncludeChatChange: (value: boolean) => void;
  onGenerate: () => void;
};

export default function ReportSourceEditor({
  selectedDate,
  notes,
  includeChat,
  hasCurrentSession,
  generating,
  onDateChange,
  onNotesChange,
  onIncludeChatChange,
  onGenerate,
}: Props) {
  return (
    <section className="report-source-editor">
      <header className="report-pane-header">
        <div>
          <span className="report-eyebrow">工作记录</span>
          <h2>整理今天的进展</h2>
        </div>
      </header>
      <label className="report-field">
        <span>日报日期</span>
        <input type="date" value={selectedDate} onChange={(event) => onDateChange(event.target.value)} />
      </label>
      <label className="report-field report-notes-field">
        <span>今日工作记录</span>
        <textarea
          aria-label="今日工作记录"
          value={notes}
          maxLength={50_000}
          placeholder="写下完成的工作、进行中的事项、问题和明日计划……"
          onChange={(event) => onNotesChange(event.target.value)}
        />
        <small>{notes.length.toLocaleString()} / 50,000</small>
      </label>
      <label className={`report-chat-toggle ${!hasCurrentSession ? 'disabled' : ''}`}>
        <input
          type="checkbox"
          aria-label="导入当前对话"
          checked={includeChat}
          disabled={!hasCurrentSession}
          onChange={(event) => onIncludeChatChange(event.target.checked)}
        />
        <span>
          <strong>导入当前对话</strong>
          <small>{hasCurrentSession ? '把当前聊天中的工作信息一起整理' : '请先在聊天页面选择一个会话'}</small>
        </span>
      </label>
      <button className="report-primary-button" disabled={generating} onClick={onGenerate}>
        {generating ? '正在生成…' : '生成汇报版日报'}
      </button>
    </section>
  );
}
