import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as reportsApi from '../api/reports';
import type { DailyReport } from '../types';
import { useDailyReports } from './useDailyReports';

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const reportAt = (date: string, version = 1, completed = '完成日报'): DailyReport => ({
  ...sampleReport,
  date,
  current_version: version,
  current: {
    ...sampleReport.current,
    number: version,
    sections: { ...sampleReport.current.sections, completed: [completed] },
  },
  versions: [{ ...sampleReport.versions[0], number: version }],
  updated_at: version,
});

vi.mock('../api/reports', async () => {
  const actual = await vi.importActual<typeof import('../api/reports')>('../api/reports');
  return {
    ...actual,
    listReports: vi.fn(),
    getReport: vi.fn(),
    generateReport: vi.fn(),
    saveReport: vi.fn(),
    reviseReport: vi.fn(),
    restoreReport: vi.fn(),
  };
});

const sampleReport: DailyReport = {
  date: '2026-08-05',
  source_notes: '记录',
  source_session_id: null,
  current_version: 1,
  current: {
    number: 1,
    kind: 'generated',
    instruction: null,
    created_at: 1,
    sections: {
      completed: ['完成日报'],
      in_progress: [],
      problems: [],
      next_day: [],
      assistance: [],
    },
  },
  versions: [{ number: 1, kind: 'generated', instruction: null, created_at: 1 }],
  created_at: 1,
  updated_at: 1,
};

describe('useDailyReports', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.listReports).mockResolvedValue([]);
    vi.mocked(reportsApi.getReport).mockResolvedValue(sampleReport);
    vi.mocked(reportsApi.generateReport).mockResolvedValue(sampleReport);
    vi.mocked(reportsApi.saveReport).mockResolvedValue(sampleReport);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('generates a report from manual notes and the current session', async () => {
    const { result } = renderHook(() => useDailyReports({ currentSessionId: 'session_1' }));
    act(() => {
      result.current.setSourceNotes('今日完成接口');
      result.current.setIncludeChat(true);
    });

    await act(async () => result.current.generate());

    expect(reportsApi.generateReport).toHaveBeenCalledWith(expect.objectContaining({
      notes: '今日完成接口',
      include_chat: true,
      session_id: 'session_1',
    }));
    expect(result.current.draftSections.completed).toEqual(['完成日报']);
  });

  it('rejects chat import without a selected session', async () => {
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));
    act(() => result.current.setIncludeChat(true));

    await act(async () => result.current.generate());

    expect(reportsApi.generateReport).not.toHaveBeenCalled();
    expect(result.current.error).toBe('请先在聊天页面选择一个会话');
  });

  it('prevents duplicate generation while a request is running', async () => {
    const pending = deferred<DailyReport>();
    vi.mocked(reportsApi.generateReport).mockReturnValue(pending.promise);
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));

    let first!: Promise<void>;
    await act(async () => {
      first = result.current.generate();
      void result.current.generate();
    });
    expect(reportsApi.generateReport).toHaveBeenCalledTimes(1);

    pending.resolve(sampleReport);
    await act(async () => first);
  });

  it('ignores an older date response that arrives after the latest selection', async () => {
    const older = deferred<DailyReport>();
    const latest = deferred<DailyReport>();
    vi.mocked(reportsApi.getReport).mockImplementation((date) => (
      date === '2026-08-04' ? older.promise : latest.promise
    ));
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));

    act(() => {
      void result.current.selectDate('2026-08-04');
      void result.current.selectDate('2026-08-03');
    });
    latest.resolve(reportAt('2026-08-03'));
    await waitFor(() => expect(result.current.report?.date).toBe('2026-08-03'));
    older.resolve(reportAt('2026-08-04'));
    await act(async () => older.promise);

    expect(result.current.selectedDate).toBe('2026-08-03');
    expect(result.current.report?.date).toBe('2026-08-03');
  });

  it('debounces manual saves and keeps local content when saving fails', async () => {
    vi.mocked(reportsApi.listReports).mockResolvedValue([
      { date: '2026-08-05', summary: '完成日报', current_version: 1, updated_at: 1 },
    ]);
    vi.mocked(reportsApi.saveReport).mockRejectedValue(new Error('保存失败'));
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));
    await waitFor(() => expect(result.current.report).not.toBeNull());
    vi.useFakeTimers();

    act(() => result.current.updateSection('completed', ['本地修改']));
    await act(() => vi.advanceTimersByTimeAsync(600));

    expect(reportsApi.saveReport).toHaveBeenCalledTimes(1);
    expect(result.current.draftSections.completed).toEqual(['本地修改']);
    expect(result.current.saveState).toBe('error');
  });

  it('keeps edits made while an earlier save is still running', async () => {
    vi.mocked(reportsApi.listReports).mockResolvedValue([
      { date: '2026-08-05', summary: '完成日报', current_version: 1, updated_at: 1 },
    ]);
    const firstSave = deferred<DailyReport>();
    vi.mocked(reportsApi.saveReport)
      .mockReturnValueOnce(firstSave.promise)
      .mockResolvedValueOnce(reportAt('2026-08-05', 3, '第二次编辑'));
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));
    await waitFor(() => expect(result.current.report).not.toBeNull());
    vi.useFakeTimers();

    act(() => result.current.updateSection('completed', ['第一次编辑']));
    act(() => vi.advanceTimersByTime(600));
    act(() => result.current.updateSection('completed', ['第二次编辑']));
    firstSave.resolve(reportAt('2026-08-05', 2, '第一次编辑'));
    await act(async () => firstSave.promise);

    expect(result.current.draftSections.completed).toEqual(['第二次编辑']);
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(reportsApi.saveReport).toHaveBeenLastCalledWith(
      '2026-08-05',
      expect.objectContaining({ completed: ['第二次编辑'] }),
      2,
    );
  });

  it('reloads the server version after a version conflict', async () => {
    const latest = reportAt('2026-08-05', 2, '其他窗口修改');
    vi.mocked(reportsApi.listReports).mockResolvedValue([
      { date: '2026-08-05', summary: '完成日报', current_version: 1, updated_at: 1 },
    ]);
    vi.mocked(reportsApi.getReport)
      .mockResolvedValueOnce(sampleReport)
      .mockResolvedValueOnce(latest);
    vi.mocked(reportsApi.saveReport).mockRejectedValue(
      new reportsApi.ReportApiError('report_version_conflict', '日报已在其他窗口更新', 409),
    );
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));
    await waitFor(() => expect(result.current.report).not.toBeNull());
    vi.useFakeTimers();

    act(() => result.current.updateSection('completed', ['本地修改']));
    await act(() => vi.advanceTimersByTimeAsync(600));

    expect(result.current.report?.current_version).toBe(2);
    expect(result.current.draftSections.completed).toEqual(['其他窗口修改']);
    expect(result.current.error).toBe('日报已在其他窗口更新');
  });

  it('retries a failed save and restores an older version', async () => {
    const restored = reportAt('2026-08-05', 2, '恢复内容');
    vi.mocked(reportsApi.listReports).mockResolvedValue([
      { date: '2026-08-05', summary: '完成日报', current_version: 1, updated_at: 1 },
    ]);
    vi.mocked(reportsApi.saveReport)
      .mockRejectedValueOnce(new Error('保存失败'))
      .mockResolvedValueOnce(reportAt('2026-08-05', 2, '本地修改'));
    vi.mocked(reportsApi.restoreReport).mockResolvedValue(restored);
    const { result } = renderHook(() => useDailyReports({ currentSessionId: '' }));
    await waitFor(() => expect(result.current.report).not.toBeNull());
    vi.useFakeTimers();

    act(() => result.current.updateSection('completed', ['本地修改']));
    await act(() => vi.advanceTimersByTimeAsync(600));
    act(() => result.current.retrySave());
    await act(() => vi.advanceTimersByTimeAsync(600));
    expect(result.current.saveState).toBe('saved');

    await act(async () => result.current.restore(1));
    expect(reportsApi.restoreReport).toHaveBeenCalledWith('2026-08-05', 1, 2);
    expect(result.current.draftSections.completed).toEqual(['恢复内容']);
  });
});
