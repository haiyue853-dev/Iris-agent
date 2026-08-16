import { useCallback, useEffect, useState } from 'react';
import { applyCuratorSuggestion, dismissCuratorSuggestion, getCuratorReport, listCuratorReports, runCurator } from '../../api/curator';
import type { CuratorReport, CuratorReportStatus, CuratorReportSummary, CuratorSuggestionKind } from '../../types';

const KIND_LABELS: Record<CuratorSuggestionKind, string> = {
  merge: '重复',
  conflict: '冲突',
  dedupe: '重复',
  expire: '过期',
  consolidate: '归纳',
};

const STATUS_LABELS: Record<CuratorReportStatus, string> = {
  open: '待处理',
  applied: '已应用',
  dismissed: '已忽略',
};

export default function CuratorPage() {
  const [reports, setReports] = useState<CuratorReportSummary[]>([]);
  const [selected, setSelected] = useState<CuratorReport | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      setReports(await listCuratorReports());
      setError(false);
    } catch {
      setError(true);
      setReports([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadReports(); }, [loadReports]);

  const run = async () => {
    setRunning(true);
    try {
      const report = await runCurator();
      setSelected(report);
      await loadReports();
      setError(false);
    } catch {
      setError(true);
    } finally {
      setRunning(false);
    }
  };

  const openReport = async (id: string) => {
    try {
      setSelected(await getCuratorReport(id));
      setError(false);
    } catch {
      setError(true);
    }
  };

  const act = async (reportId: string, action: 'apply' | 'dismiss', suggestionIds?: string[]) => {
    try {
      if (action === 'apply') {
        await applyCuratorSuggestion(reportId, suggestionIds);
      } else {
        await dismissCuratorSuggestion(reportId, suggestionIds);
      }
      setSelected(await getCuratorReport(reportId));
      await loadReports();
      setError(false);
    } catch {
      setError(true);
    }
  };

  const formatTime = (iso: string) => {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
  };

  return (
    <section className="memory-page" aria-label="审查">
      <header className="memory-header">
        <span>CURATOR</span>
        <h1>后台审查</h1>
        <p>定期审查记忆与画像中的重复、冲突内容，确认后应用。</p>
      </header>

      <div className="memory-form">
        <button className="curator-run" onClick={() => void run()} disabled={running}>
          {running ? '审查中…' : '立即审查'}
        </button>
      </div>

      {error && <div className="memory-error" role="alert">审查服务暂不可用。</div>}

      {loading ? (
        <p className="memory-empty">正在加载审查报告…</p>
      ) : reports.length === 0 && !selected ? (
        <p className="memory-empty">还没有审查报告，点击「立即审查」开始</p>
      ) : (
        <div className="curator-layout">
          <ul className="memory-list curator-reports">
            {reports.map((report) => (
              <li
                key={report.id}
                className={`memory-item ${selected?.id === report.id ? 'curator-selected' : ''}`}
                onClick={() => void openReport(report.id)}
              >
                <span className={`curator-status curator-status-${report.status}`}>{STATUS_LABELS[report.status]}</span>
                <span className="memory-content">{report.summary}</span>
                <span className="curator-time">{formatTime(report.created_at)}</span>
              </li>
            ))}
          </ul>

          {selected && (
            <div className="curator-detail">
              <h2>{selected.summary}</h2>
              {selected.suggestions.length === 0 ? (
                <p className="memory-empty">本报告没有需要处理的建议</p>
              ) : (
                <>
                  <div className="curator-actions">
                    <button onClick={() => void act(selected.id, 'apply')}>全部应用</button>
                    <button onClick={() => void act(selected.id, 'dismiss')}>全部忽略</button>
                  </div>
                  <ul className="memory-list">
                    {selected.suggestions.map((suggestion) => (
                      <li key={suggestion.id} className="memory-item curator-suggestion">
                        <span className={`curator-kind curator-kind-${suggestion.kind}`}>{KIND_LABELS[suggestion.kind]}</span>
                        <span className="memory-content">
                          {suggestion.summary}
                          {suggestion.resolution && (
                            <span className="curator-resolution">→ {suggestion.resolution}</span>
                          )}
                        </span>
                        <span className="curator-reason">{suggestion.reason === 'llm' ? 'LLM' : suggestion.reason === 'embedding' ? '向量' : suggestion.reason === 'age' ? '时效' : '重叠'}</span>
                        {suggestion.applied ? (
                          <span className="curator-done">已应用</span>
                        ) : suggestion.dismissed ? (
                          <span className="curator-done">已忽略</span>
                        ) : (
                          <>
                            <button className="curator-apply" onClick={() => void act(selected.id, 'apply', [suggestion.id])}>应用</button>
                            <button className="curator-dismiss" onClick={() => void act(selected.id, 'dismiss', [suggestion.id])}>忽略</button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
