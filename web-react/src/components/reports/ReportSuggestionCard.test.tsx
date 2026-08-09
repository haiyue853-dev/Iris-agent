import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ReportSuggestion } from '../../types';
import ReportSuggestionCard from './ReportSuggestionCard';

const suggestion: ReportSuggestion = {
  id: 'suggestion_1',
  reply: '已整理为一份日报建议。',
  sections: {
    completed: ['完成日报工作台'],
    in_progress: ['完善交互'],
    problems: ['等待接口'],
    next_day: ['验证构建'],
    assistance: ['需要产品确认'],
  },
  attachment_ids: ['attachment_1'],
  applied: false,
};

describe('ReportSuggestionCard', () => {
  it('shows all report sections and applies only after the user confirms', async () => {
    const onApply = vi.fn();
    render(<ReportSuggestionCard suggestion={suggestion} busy={false} onApply={onApply} />);

    expect(screen.getByText('今日完成')).toBeInTheDocument();
    expect(screen.getByText('进行中')).toBeInTheDocument();
    expect(screen.getByText('问题与风险')).toBeInTheDocument();
    expect(screen.getByText('明日计划')).toBeInTheDocument();
    expect(screen.getByText('需要协助')).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: '应用到日报' }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });
});

