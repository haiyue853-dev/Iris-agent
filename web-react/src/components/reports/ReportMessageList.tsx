import type { ReportChatMessage } from '../../types';

export default function ReportMessageList({ messages }: { messages: ReportChatMessage[] }) {
  if (messages.length === 0) {
    return <p className="report-chat-empty" role="status">在这里告诉 Iris 你想突出哪些工作成果；建议需要确认后才会写入日报。</p>;
  }
  return <ol className="report-message-list" aria-label="日报对话记录">
    {messages.map((message) => <li className={`report-message ${message.role}`} key={message.id}>
      <strong>{message.role === 'user' ? '你' : 'Iris'}</strong>
      <p>{message.content}</p>
    </li>)}
  </ol>;
}

