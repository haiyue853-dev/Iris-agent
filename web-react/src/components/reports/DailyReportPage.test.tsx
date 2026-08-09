import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as reportsApi from '../../api/reports';
import type { DailyReport } from '../../types';
import DailyReportPage from './DailyReportPage';

const { ensureWorkspace } = vi.hoisted(() => ({ ensureWorkspace: vi.fn() }));

vi.mock('../../api/reports', async () => {
  const actual = await vi.importActual<typeof import('../../api/reports')>('../../api/reports');
  return {
    ...actual,
    listReports: vi.fn(),
    getReport: vi.fn(),
    generateReport: vi.fn(),
    ensureReportWorkspace: ensureWorkspace,
    saveReport: vi.fn(),
    reviseReport: vi.fn(),
    restoreReport: vi.fn(),
  };
});

const generated: DailyReport = {
  date: new Date().toLocaleDateString('en-CA'),
  source_notes: '完成日报页面',
  source_session_id: 'session_1',
  current_version: 1,
  revision: 1,
  current: {
    number: 1,
    kind: 'generated',
    instruction: null,
    created_at: 1,
    sections: {
      completed: ['完成日报页面'],
      in_progress: [],
      problems: [],
      next_day: ['接入预览'],
      assistance: [],
    },
  },
  versions: [{ number: 1, kind: 'generated', instruction: null, created_at: 1 }],
  created_at: 1,
  updated_at: 1,
};

const workspaceDraft: DailyReport = {
  ...generated,
  source_notes: '',
  source_session_id: null,
  current: {
    ...generated.current,
    sections: {
      completed: [],
      in_progress: [],
      problems: [],
      next_day: [],
      assistance: [],
    },
  },
};

describe('DailyReportPage', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.listReports).mockResolvedValue([]);
    vi.mocked(reportsApi.generateReport).mockResolvedValue(generated);
    ensureWorkspace.mockResolvedValue(workspaceDraft);
  });

  afterEach(() => cleanup());

  it('shows the workspace upload and AI chat controls on first entry', async () => {
    render(<DailyReportPage currentSessionId="session_1" />);

    expect(await screen.findByRole('button', { name: '添加文件' })).toBeEnabled();
    expect(screen.getByLabelText('日报对话内容')).toBeEnabled();
    const reportDate = screen.getByLabelText('日报日期');
    expect(reportDate).toBeEnabled();
    expect(reportDate).toHaveAttribute('type', 'date');
    expect(reportDate.parentElement).toHaveClass('report-field');
    expect(reportDate.parentElement?.parentElement).toHaveClass('report-source-editor');
    expect(screen.getByText('日报草稿已就绪。可从工作记录、附件或对话开始，确认 AI 建议后会在这里更新。')).toBeInTheDocument();
    expect(ensureWorkspace).toHaveBeenCalledWith(workspaceDraft.date);
  });

  it('generates a report and exposes copy, download, and revision controls', async () => {
    render(<DailyReportPage currentSessionId="session_1" />);
    await userEvent.type(screen.getByLabelText('今日工作记录'), '完成日报页面');
    await userEvent.click(screen.getByLabelText('导入当前对话'));
    await userEvent.click(screen.getByRole('button', { name: '生成汇报版日报' }));

    expect(await screen.findByLabelText('今日完成')).toHaveValue('完成日报页面');
    expect(screen.getByRole('button', { name: '复制' })).toBeEnabled();
    expect(screen.getByRole('link', { name: '下载 .md' })).toHaveAttribute('href');
    expect(screen.getByLabelText('AI 修改要求')).toBeInTheDocument();
  });

  it('locks report inputs while a historical version is restoring', async () => {
    const restorable: DailyReport = {
      ...generated,
      current_version: 2,
      revision: 2,
      current: { ...generated.current, number: 2, kind: 'manual' },
      versions: [
        generated.versions[0],
        { number: 2, kind: 'manual', instruction: null, created_at: 2 },
      ],
    };
    ensureWorkspace.mockResolvedValue(restorable);
    vi.mocked(reportsApi.restoreReport).mockImplementation(() => new Promise<DailyReport>(() => {}));

    render(<DailyReportPage currentSessionId="session_1" />);
    await userEvent.click(await screen.findByRole('button', { name: '恢复' }));

    expect(screen.getByLabelText('日报日期')).toBeDisabled();
    expect(screen.getByLabelText('今日工作记录')).toBeDisabled();
    expect(screen.getByLabelText('导入当前对话')).toBeDisabled();
    expect(screen.getByRole('button', { name: '添加文件' })).toBeDisabled();
    expect(screen.getByLabelText('日报对话内容')).toBeDisabled();
    const previewInputs = document.querySelectorAll<HTMLTextAreaElement>('.report-preview textarea');
    expect(previewInputs).toHaveLength(5);
    previewInputs.forEach((input) => expect(input).toBeDisabled());
  });
});
