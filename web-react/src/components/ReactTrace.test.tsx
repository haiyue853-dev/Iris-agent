import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ReactTrace from './ReactTrace';

describe('ReactTrace', () => {
  it('shows the agent plan, action, and observation without the final response', () => {
    render(<ReactTrace steps={[
      { phase: 'thought', content: '先查询资料', round: 1 },
      { phase: 'action', call_id: 'call-1', name: 'search', arguments: {}, round: 1 },
      { phase: 'observation', call_id: 'call-1', name: 'search', ok: true, result: {} },
      { phase: 'final', content: '完成' },
    ]} />);

    expect(screen.getByLabelText('智能体执行轨迹')).toBeInTheDocument();
    expect(screen.getByText('先查询资料')).toBeInTheDocument();
    expect(screen.getByText('调用 search')).toBeInTheDocument();
    expect(screen.getByText('search 已返回结果')).toBeInTheDocument();
    expect(screen.queryByText('完成')).not.toBeInTheDocument();
  });
});
