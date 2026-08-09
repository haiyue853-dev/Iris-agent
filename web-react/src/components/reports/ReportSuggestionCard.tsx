import type { ReportSuggestion } from '../../types';

const sectionLabels: Array<[keyof ReportSuggestion['sections'], string]> = [
  ['completed', '今日完成'],
  ['in_progress', '进行中'],
  ['problems', '问题与风险'],
  ['next_day', '明日计划'],
  ['assistance', '需要协助'],
];

export default function ReportSuggestionCard({ suggestion, busy, onApply }: { suggestion: ReportSuggestion | null; busy: boolean; onApply: () => void }) {
  if (!suggestion) return null;
  return <section className="report-suggestion" aria-label="AI 日报建议">
    <strong>AI 建议</strong>
    <p>{suggestion.reply}</p>
    <div className="report-suggestion-sections">
      {sectionLabels.map(([key, label]) => <section key={key}>
        <h3>{label}</h3>
        {suggestion.sections[key].length === 0 ? <p>暂无内容</p> : <ul>{suggestion.sections[key].map((item, index) => <li key={`${key}-${index}`}>{item}</li>)}</ul>}
      </section>)}
    </div>
    <button className="report-primary-button" disabled={busy || suggestion.applied} onClick={onApply}>{suggestion.applied ? '已应用到日报' : '应用到日报'}</button>
  </section>;
}

