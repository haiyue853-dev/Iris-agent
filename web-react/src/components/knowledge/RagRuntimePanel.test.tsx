import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import RagRuntimePanel from './RagRuntimePanel';
import type { KnowledgeRuntime } from '../../api/knowledge';

const runtime: KnowledgeRuntime = {
  config: {
    embedding_enabled: true, embedding_model: 'bge-m3', embedding_base_url: 'http://localhost:11434',
    semantic_split_enabled: true, semantic_split_model: 'bge-m3', semantic_split_base_url: 'http://localhost:11434',
    graph_enabled: true, graph_model: 'deepseek-r1:8b', graph_base_url: 'http://localhost:11434',
    image_enabled: false, image_model: 'qwen2.5vl:7b', image_base_url: 'http://localhost:11434',
    reranker_enabled: true, reranker_provider: 'ollama', reranker_model: 'deepseek-r1:8b', reranker_base_url: 'http://localhost:11434',
    mmr_relevance_weight: 0.7,
  },
  components: [
    { key: 'embedding', label: '向量模型', enabled: true, provider: 'ollama', model: 'bge-m3', base_url: 'http://localhost:11434', status: 'connected', message: '服务可用，模型已安装', latency_ms: 12 },
    { key: 'graph', label: '图谱模型', enabled: true, provider: 'ollama', model: 'deepseek-r1:8b', base_url: 'http://localhost:11434', status: 'failed', message: '模型未安装', latency_ms: 4 },
    { key: 'image', label: '视觉解析', enabled: false, provider: 'ollama', model: 'qwen2.5vl:7b', base_url: 'http://localhost:11434', status: 'disabled', message: '已停用', latency_ms: null },
    { key: 'reranker', label: '重排模型', enabled: true, provider: 'ollama', model: 'deepseek-r1:8b', base_url: 'http://localhost:11434', status: 'untested', message: '尚未测试', latency_ms: null },
  ],
};

describe('RagRuntimePanel', () => {
  it('shows component health and runs a full connection test', async () => {
    const onTest = vi.fn();
    render(<RagRuntimePanel runtime={runtime} saving={false} testing={false} onSave={vi.fn()} onTest={onTest} />);

    expect(screen.getByText('服务可用，模型已安装')).toBeInTheDocument();
    expect(screen.getByText('模型未安装')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '检测全部连接' }));

    expect(onTest).toHaveBeenCalledWith();
  });

  it('edits and saves the runtime model configuration', async () => {
    const onSave = vi.fn();
    render(<RagRuntimePanel runtime={runtime} saving={false} testing={false} onSave={onSave} onTest={vi.fn()} />);

    await userEvent.click(screen.getByRole('button', { name: '编辑模型配置' }));
    expect(screen.getByRole('option', { name: '本地 FastEmbed' })).toBeInTheDocument();
    const model = screen.getByLabelText('向量模型');
    await userEvent.clear(model);
    await userEvent.type(model, 'nomic-embed-text');
    await userEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ embedding_model: 'nomic-embed-text' }));
  });

  it('collapses the editor after a successful save', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<RagRuntimePanel runtime={runtime} saving={false} testing={false} onSave={onSave} onTest={vi.fn()} />);

    await userEvent.click(screen.getByRole('button', { name: '编辑模型配置' }));
    await userEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    expect(screen.getByRole('button', { name: '编辑模型配置' })).toBeInTheDocument();
  });
});
