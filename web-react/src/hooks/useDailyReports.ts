import { useCallback, useEffect, useRef, useState } from 'react';

import {
  ReportApiError,
  downloadReportUrl,
  generateReport,
  getReport,
  listReports,
  restoreReport,
  reviseReport,
  saveReport,
} from '../api/reports';
import type { DailyReport, ReportSections, ReportSummary } from '../types';

export type SaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';
export type BusyAction = 'generate' | 'revise' | 'restore' | null;
export type ReportPane = 'history' | 'source' | 'preview';

const emptySections = (): ReportSections => ({
  completed: [],
  in_progress: [],
  problems: [],
  next_day: [],
  assistance: [],
});

const localDate = (): string => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const errorMessage = (error: unknown): string => (
  error instanceof Error ? error.message : '操作失败，请稍后重试'
);

const markdownFrom = (reportDate: string, sections: ReportSections): string => {
  const [year, month, day] = reportDate.split('-').map(Number);
  const blocks: Array<[string, string[]]> = [
    ['今日完成', sections.completed],
    ['进行中', sections.in_progress],
    ['遇到的问题', sections.problems],
    ['明日计划', sections.next_day],
    ['需要协助', sections.assistance],
  ];
  return [
    `# ${year} 年 ${month} 月 ${day} 日工作日报`,
    ...blocks.map(([title, items]) => `## ${title}\n${items.length ? items.map((item) => `- ${item}`).join('\n') : '- 无'}`),
  ].join('\n\n') + '\n';
};

export function useDailyReports({ currentSessionId }: { currentSessionId: string }) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selectedDate, setSelectedDate] = useState(localDate);
  const [report, setReport] = useState<DailyReport | null>(null);
  const [draftSections, setDraftSections] = useState<ReportSections>(emptySections);
  const [sourceNotes, setSourceNotesState] = useState('');
  const [includeChat, setIncludeChat] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [error, setError] = useState('');
  const [activeMobilePane, setActiveMobilePane] = useState<ReportPane>('source');
  const [saveNonce, setSaveNonce] = useState(0);
  const reportRef = useRef<DailyReport | null>(null);
  const draftRef = useRef<ReportSections>(draftSections);
  const selectedDateRef = useRef(selectedDate);
  const requestRef = useRef(0);
  const busyActionRef = useRef<BusyAction>(null);
  const editRevisionRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const saveQueuedRef = useRef(false);

  const syncSummary = useCallback((next: DailyReport) => {
    const summary: ReportSummary = {
      date: next.date,
      summary: next.current.sections.completed[0] || '暂无内容',
      current_version: next.current_version,
      updated_at: next.updated_at,
    };
    setReports((current) => [summary, ...current.filter((item) => item.date !== next.date)]
      .sort((a, b) => b.updated_at - a.updated_at));
  }, []);

  const applyReport = useCallback((next: DailyReport) => {
    reportRef.current = next;
    draftRef.current = next.current.sections;
    editRevisionRef.current = 0;
    setReport(next);
    setDraftSections(next.current.sections);
    setSourceNotesState(next.source_notes);
    setIncludeChat(Boolean(next.source_session_id));
    setSaveState('saved');
    syncSummary(next);
  }, [syncSummary]);

  const clearReport = useCallback(() => {
    reportRef.current = null;
    draftRef.current = emptySections();
    editRevisionRef.current = 0;
    setReport(null);
    setDraftSections(draftRef.current);
    setSourceNotesState('');
    setIncludeChat(false);
    setSaveState('idle');
  }, []);

  useEffect(() => {
    let cancelled = false;
    const initialDate = selectedDateRef.current;
    listReports()
      .then(async (items) => {
        if (cancelled) return;
        setReports(items);
        if (items.some((item) => item.date === initialDate)) {
          const loaded = await getReport(initialDate);
          if (!cancelled && selectedDateRef.current === initialDate) applyReport(loaded);
        }
      })
      .catch((caught) => {
        if (!cancelled) setError(errorMessage(caught));
      });
    return () => { cancelled = true; };
  }, [applyReport]);

  useEffect(() => {
    if (saveNonce === 0) return;
    const timer = window.setTimeout(async () => {
      const current = reportRef.current;
      if (!current) return;
      if (saveInFlightRef.current) {
        saveQueuedRef.current = true;
        return;
      }
      const expectedVersion = current.current_version;
      const date = current.date;
      const editRevision = editRevisionRef.current;
      const sections = Object.fromEntries(
        Object.entries(draftRef.current).map(([key, items]) => [key, [...items]]),
      ) as ReportSections;
      saveInFlightRef.current = true;
      setSaveState('saving');
      try {
        const saved = await saveReport(date, sections, expectedVersion);
        if (selectedDateRef.current === date && reportRef.current?.current_version === expectedVersion) {
          if (editRevisionRef.current === editRevision) {
            applyReport(saved);
          } else {
            reportRef.current = saved;
            setReport(saved);
            syncSummary(saved);
            setSaveState('dirty');
            setSaveNonce((currentNonce) => currentNonce + 1);
          }
        }
      } catch (caught) {
        if (caught instanceof ReportApiError && caught.code === 'report_version_conflict') {
          try {
            const latest = await getReport(date);
            if (selectedDateRef.current === date) applyReport(latest);
          } catch {
            setSaveState('error');
          }
        } else {
          setSaveState('error');
        }
        setError(errorMessage(caught));
      } finally {
        saveInFlightRef.current = false;
        if (saveQueuedRef.current) {
          saveQueuedRef.current = false;
          setSaveNonce((currentNonce) => currentNonce + 1);
        }
      }
    }, 600);
    return () => window.clearTimeout(timer);
  }, [applyReport, saveNonce, syncSummary]);

  const selectDate = useCallback(async (date: string) => {
    const request = ++requestRef.current;
    selectedDateRef.current = date;
    setSelectedDate(date);
    setError('');
    try {
      const loaded = await getReport(date);
      if (request === requestRef.current) applyReport(loaded);
    } catch (caught) {
      if (request !== requestRef.current) return;
      if (caught instanceof ReportApiError && caught.code === 'report_not_found') {
        clearReport();
      } else {
        setError(errorMessage(caught));
      }
    }
  }, [applyReport, clearReport]);

  const setSourceNotes = useCallback((value: string) => {
    setSourceNotesState(value);
  }, []);

  const generate = useCallback(async () => {
    if (busyActionRef.current) return;
    if (includeChat && !currentSessionId) {
      setError('请先在聊天页面选择一个会话');
      return;
    }
    busyActionRef.current = 'generate';
    setBusyAction('generate');
    setError('');
    try {
      const generated = await generateReport({
        date: selectedDate,
        notes: sourceNotes,
        include_chat: includeChat,
        session_id: includeChat ? currentSessionId : null,
        expected_version: reportRef.current?.current_version ?? null,
      });
      applyReport(generated);
      setActiveMobilePane('preview');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }, [applyReport, currentSessionId, includeChat, selectedDate, sourceNotes]);

  const updateSection = useCallback((key: keyof ReportSections, items: string[]) => {
    setDraftSections((current) => {
      const next = { ...current, [key]: items };
      draftRef.current = next;
      editRevisionRef.current += 1;
      return next;
    });
    setSaveState('dirty');
    setSaveNonce((current) => current + 1);
  }, []);

  const retrySave = useCallback(() => {
    if (reportRef.current) {
      setSaveState('dirty');
      setSaveNonce((current) => current + 1);
    }
  }, []);

  const revise = useCallback(async (instruction: string) => {
    const current = reportRef.current;
    if (!current || busyActionRef.current) return;
    busyActionRef.current = 'revise';
    setBusyAction('revise');
    setError('');
    try {
      applyReport(await reviseReport(current.date, instruction, current.current_version));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }, [applyReport]);

  const restore = useCallback(async (version: number) => {
    const current = reportRef.current;
    if (!current || busyActionRef.current) return;
    busyActionRef.current = 'restore';
    setBusyAction('restore');
    setError('');
    try {
      applyReport(await restoreReport(current.date, version, current.current_version));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }, [applyReport]);

  const copyMarkdown = useCallback(async () => {
    await navigator.clipboard.writeText(markdownFrom(selectedDateRef.current, draftRef.current));
  }, []);

  return {
    reports,
    selectedDate,
    report,
    draftSections,
    sourceNotes,
    includeChat,
    saveState,
    busyAction,
    error,
    activeMobilePane,
    selectDate,
    setSourceNotes,
    setIncludeChat,
    generate,
    updateSection,
    revise,
    restore,
    retrySave,
    copyMarkdown,
    downloadUrl: report ? downloadReportUrl(report.date) : '',
    setActiveMobilePane,
  };
}
