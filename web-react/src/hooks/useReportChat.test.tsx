import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as reportsApi from '../api/reports';
import type { DailyReport, ReportChatResponse } from '../types';
import { useReportChat } from './useReportChat';

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
};

vi.mock('../api/reports', async () => {
  const actual = await vi.importActual<typeof import('../api/reports')>('../api/reports');
  return { ...actual, chatAboutReport: vi.fn() };
});

const report: DailyReport = {
  date: '2026-08-09',
  source_notes: '',
  source_session_id: null,
  current_version: 2,
  revision: 7,
  current: {
    number: 2,
    kind: 'manual',
    instruction: null,
    created_at: 2,
    sections: { completed: [], in_progress: [], problems: [], next_day: [], assistance: [] },
  },
  versions: [
    { number: 1, kind: 'generated', instruction: null, created_at: 1 },
    { number: 2, kind: 'manual', instruction: null, created_at: 2 },
  ],
  created_at: 1,
  updated_at: 2,
};

const chatResponse: ReportChatResponse = {
  reply: 'Iris 建议先突出今天完成的事项。',
  suggestion: {
    id: 'suggestion_1',
    reply: 'Iris 建议先突出今天完成的事项。',
    sections: { completed: ['完成恢复功能'], in_progress: [], problems: [], next_day: [], assistance: [] },
    attachment_ids: [],
    applied: false,
  },
};

describe('useReportChat', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.chatAboutReport).mockResolvedValue(chatResponse);
  });

  afterEach(() => vi.clearAllMocks());

  it('clears an unapplied suggestion when the current report revision changes', async () => {
    const { result, rerender } = renderHook(
      ({ currentReport }: { currentReport: DailyReport }) => useReportChat({
        report: currentReport,
        onReportUpdated: vi.fn(),
        onError: vi.fn(),
      }),
      { initialProps: { currentReport: report } },
    );

    await act(async () => { await result.current.send('请整理今天的工作'); });
    expect(result.current.suggestion).toEqual(chatResponse.suggestion);

    rerender({ currentReport: { ...report, revision: 8, current_version: 1 } });

    await waitFor(() => expect(result.current.suggestion).toBeNull());
  });

  it('drops a chat response that was generated for an earlier report revision', async () => {
    const pending = deferred<ReportChatResponse>();
    vi.mocked(reportsApi.chatAboutReport).mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(
      ({ currentReport }: { currentReport: DailyReport }) => useReportChat({
        report: currentReport,
        onReportUpdated: vi.fn(),
        onError: vi.fn(),
      }),
      { initialProps: { currentReport: report } },
    );

    let sending!: Promise<void>;
    act(() => { sending = result.current.send('请整理今天的工作'); });
    rerender({ currentReport: { ...report, revision: 8, current_version: 1 } });
    pending.resolve(chatResponse);
    await act(async () => sending);

    expect(result.current.suggestion).toBeNull();
    expect(result.current.messages).toEqual([]);
  });
});
