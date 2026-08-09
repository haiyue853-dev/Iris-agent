import { useState } from 'react';

type Props = { disabled: boolean; onSend: (message: string) => void };

export default function ReportChat({ disabled, onSend }: Props) {
  const [message, setMessage] = useState('');
  const submit = () => { if (!disabled && message.trim()) { onSend(message); setMessage(''); } };
  return <section className="report-chat" aria-label="日报 AI 对话">
    <div className="report-chat-heading"><span className="report-eyebrow">日报助手</span><h2>告诉 Iris 如何整理</h2></div>
    <p className="report-muted">选择附件后提问，Iris 会先给出建议；确认后才会写入右侧日报。</p>
    <textarea aria-label="日报对话内容" value={message} disabled={disabled} placeholder="例如：根据附件整理今日完成和风险" onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); submit(); } }} />
    <button className="report-primary-button" disabled={disabled || !message.trim()} onClick={submit}>发送</button>
  </section>;
}

