import { useCallback, useEffect, useRef, useState } from 'react';

import {
  ReportApiError,
  downloadReportUrl,
  ensureReportWorkspace,
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

type SaveIntent = {
  epoch: number;
  cancellation: number;
  date: string;
  expectedRevision: number;
  sections: ReportSections;
  editRevision: number;
  selectionRequest: number;
};

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
  const [previewJumpKey, setPreviewJumpKey] = useState(0);
  const [saveIntent, setSaveIntent] = useState<SaveIntent | null>(null);
  const reportRef = useRef<DailyReport | null>(null);
  const draftRef = useRef<ReportSections>(draftSections);
  const selectedDateRef = useRef(selectedDate);
  const requestRef = useRef(0);
  const busyActionRef = useRef<BusyAction>(null);
  const editRevisionRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const autoSaveEpochRef = useRef(0);
  const saveCancellationRef = useRef(0);
  const saveQueuedEpochRef = useRef<number | null>(null);
  const saveCompletionRef = useRef<Promise<void> | null>(null);

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

  const invalidateAutoSave = useCallback(() => {
    autoSaveEpochRef.current += 1;
    saveCancellationRef.current += 1;
    saveQueuedEpochRef.current = null;
    setSaveIntent(null);
  }, []);

  const queueSave = useCallback((sections: ReportSections = draftRef.current) => {
    const current = reportRef.current;
    if (!current) return;
    const copiedSections = Object.fromEntries(
      Object.entries(sections).map(([key, items]) => [key, [...items]]),
    ) as ReportSections;
    const epoch = ++autoSaveEpochRef.current;
    setSaveIntent({
      epoch,
      cancellation: saveCancellationRef.current,
      date: current.date,
      expectedRevision: current.revision,
      sections: copiedSections,
      editRevision: editRevisionRef.current,
      selectionRequest: requestRef.current,
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const initialDate = selectedDateRef.current;
    listReports()
      .then((items) => {
        if (!cancelled) {
          setReports((current) => [...items, ...current.filter((item) => !items.some((next) => next.date === item.date))]
            .sort((a, b) => b.updated_at - a.updated_at));
        }
      })
      .catch((caught) => { if (!cancelled) setError(errorMessage(caught)); });
    ensureReportWorkspace(initialDate)
      .then((workspace) => {
        if (!cancelled && selectedDateRef.current === initialDate) applyReport(workspace);
      })
      .catch((caught) => { if (!cancelled) setError(errorMessage(caught)); });
    return () => { cancelled = true; };
  }, [applyReport]);

  useEffect(() => {
    if (!saveIntent) return;
    const intent = saveIntent;
    const timer = window.setTimeout(async () => {
      if (
        intent.epoch !== autoSaveEpochRef.current
        || intent.cancellation !== saveCancellationRef.current
        || intent.selectionRequest !== requestRef.current
        || selectedDateRef.current !== intent.date
      ) return;
      if (saveInFlightRef.current) {
        saveQueuedEpochRef.current = intent.epoch;
        return;
      }
      saveInFlightRef.current = true;
      setSaveState('saving');
      let completion!: Promise<void>;
      const stillSelected = () => (
        intent.selectionRequest === requestRef.current
        && selectedDateRef.current === intent.date
        && reportRef.current?.date === intent.date
      );
      const stillSavingThisReport = () => (
        stillSelected() && reportRef.current?.revision === intent.expectedRevision
      );
      const runSave = async () => {
        try {
          const saved = await saveReport(intent.date, intent.sections, intent.expectedRevision);
          if (stillSavingThisReport()) {
            if (editRevisionRef.current === intent.editRevision) {
              applyReport(saved);
            } else {
              reportRef.current = saved;
              setReport(saved);
              syncSummary(saved);
              setSaveState('dirty');
              if (intent.cancellation === saveCancellationRef.current) {
                queueSave(draftRef.current);
              }
            }
          }
        } catch (caught) {
          if (!stillSelected()) return;
          if (caught instanceof ReportApiError && caught.code === 'report_version_conflict') {
            try {
              const latest = await getReport(intent.date);
              if (stillSelected() && editRevisionRef.current === intent.editRevision) applyReport(latest);
            } catch {
              if (stillSelected()) setSaveState('error');
            }
          } else {
            setSaveState('error');
          }
          setError(errorMessage(caught));
        } finally {
          saveInFlightRef.current = false;
          if (saveCompletionRef.current === completion) saveCompletionRef.current = null;
          if (
            intent.cancellation === saveCancellationRef.current
            && saveQueuedEpochRef.current === autoSaveEpochRef.current
          ) {
            saveQueuedEpochRef.current = null;
            queueSave(draftRef.current);
          }
        }
      };
      completion = runSave();
      saveCompletionRef.current = completion;
    }, 600);
    return () => window.clearTimeout(timer);
  }, [applyReport, queueSave, saveIntent, syncSummary]);

  const selectDate = useCallback(async (date: string) => {
    invalidateAutoSave();
    const request = ++requestRef.current;
    selectedDateRef.current = date;
    setSelectedDate(date);
    setError('');
    try {
      const loaded = await ensureReportWorkspace(date);
      if (request === requestRef.current) applyReport(loaded);
    } catch (caught) {
      if (request !== requestRef.current) return;
      setError(errorMessage(caught));
    }
  }, [applyReport, invalidateAutoSave]);

  const setSourceNotes = useCallback((value: string) => {
    setSourceNotesState(value);
  }, []);

  const generate = useCallback(async () => {
    if (busyActionRef.current) return;
    if (includeChat && !currentSessionId) {
      setError('请先在聊天页面选择一个会话');
      return;
    }
    invalidateAutoSave();
    busyActionRef.current = 'generate';
    setBusyAction('generate');
    setError('');
    try {
      const generated = await generateReport({
        date: selectedDate,
        notes: sourceNotes,
        include_chat: includeChat,
        session_id: includeChat ? currentSessionId : null,
        expected_revision: reportRef.current?.revision ?? null,
      });
      applyReport(generated);
      setActiveMobilePane('preview');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }, [applyReport, currentSessionId, includeChat, invalidateAutoSave, selectedDate, sourceNotes]);

  const updateSection = useCallback((key: keyof ReportSections, items: string[]) => {
    const next = { ...draftRef.current, [key]: items };
    draftRef.current = next;
    editRevisionRef.current += 1;
    setDraftSections(next);
    setSaveState('dirty');
    queueSave(next);
  }, [queueSave]);

  const retrySave = useCallback(() => {
    if (reportRef.current) {
      setSaveState('dirty');
      queueSave();
    }
  }, [queueSave]);

  const revise = useCallback(async (instruction: string) => {
    const current = reportRef.current;
    if (!current || busyActionRef.current) return;
    invalidateAutoSave();
    busyActionRef.current = 'revise';
    setBusyAction('revise');
    setError('');
    try {
      applyReport(await reviseReport(current.date, instruction, current.revision));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }, [applyReport, invalidateAutoSave]);

  const restore = useCallback(async (version: number) => {
    let current = reportRef.current;
    if (!current || busyActionRef.current) return;
    const date = current.date;
    const selectionRequest = requestRef.current;
    invalidateAutoSave();
    busyActionRef.current = 'restore';
    setBusyAction('restore');
    setError('');
    try {
      await saveCompletionRef.current;
      if (selectionRequest !== requestRef.current || selectedDateRef.current !== date) return;
      current = reportRef.current;
      if (!current || current.date !== date) return;
      const restored = await restoreReport(date, version, current.revision);
      if (selectionRequest !== requestRef.current || selectedDateRef.current !== date) {
        syncSummary(restored);
        return;
      }
      applyReport(restored);
      setActiveMobilePane('preview');
      setPreviewJumpKey((currentKey) => currentKey + 1);
    } catch (caught) {
      if (selectionRequest === requestRef.current && selectedDateRef.current === date) {
        setError(errorMessage(caught));
      }
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }, [applyReport, invalidateAutoSave, syncSummary]);

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
    previewJumpKey,
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
    applyExternalReport: (next: DailyReport) => {
      invalidateAutoSave();
      applyReport(next);
    },
    setExternalError: setError,
  };
}
