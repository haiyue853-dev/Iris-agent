import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, CircleOff, LoaderCircle, SlidersHorizontal, XCircle } from 'lucide-react';

import type { KnowledgeRuntime, KnowledgeRuntimeConfig } from '../../api/knowledge';

type Props = {
  runtime: KnowledgeRuntime;
  saving: boolean;
  testing: boolean;
  onSave: (config: KnowledgeRuntimeConfig) => void | Promise<void>;
  onTest: (component?: 'embedding' | 'graph' | 'image' | 'reranker') => void | Promise<void>;
};

const statusLabel = { connected: '可用', failed: '异常', disabled: '已停用', untested: '未测试' } as const;

function StatusIcon({ status }: { status: KnowledgeRuntime['components'][number]['status'] }) {
  if (status === 'connected') return <CheckCircle2 aria-hidden="true" />;
  if (status === 'failed') return <XCircle aria-hidden="true" />;
  if (status === 'disabled') return <CircleOff aria-hidden="true" />;
  return <Activity aria-hidden="true" />;
}

export default function RagRuntimePanel({ runtime, saving, testing, onSave, onTest }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(runtime.config);
  const [saveError, setSaveError] = useState('');
  useEffect(() => setDraft(runtime.config), [runtime.config]);
  const edit = <K extends keyof KnowledgeRuntimeConfig>(key: K, value: KnowledgeRuntimeConfig[K]) => setDraft((current) => ({ ...current, [key]: value }));

  return <details className="knowledge-runtime" open>
    <summary><span><Activity aria-hidden="true" />RAG 运行状态</span><small>模型连接、索引能力与运行配置</small></summary>
    <div className="knowledge-runtime-body">
      <div className="knowledge-runtime-toolbar">
        <p>配置保存后立即作用于新检索和新导入资料。</p>
        <div><button onClick={() => void onTest()} disabled={testing}>{testing ? <><LoaderCircle className="spin" aria-hidden="true" />检测中…</> : '检测全部连接'}</button><button onClick={() => setEditing((value) => !value)}><SlidersHorizontal aria-hidden="true" />{editing ? '收起配置' : '编辑模型配置'}</button></div>
      </div>
      <div className="knowledge-runtime-grid">
        {runtime.components.map((component) => <article className={`knowledge-runtime-card ${component.status}`} key={component.key}>
          <div><span className="knowledge-runtime-status"><StatusIcon status={component.status} />{statusLabel[component.status]}</span><button onClick={() => void onTest(component.key)} disabled={testing || !component.enabled}>检测</button></div>
          <strong>{component.label}</strong><code>{component.model}</code>
          <small><span>{component.message}</span>{component.latency_ms !== null ? ` · ${component.latency_ms} ms` : ''}</small>
        </article>)}
      </div>
      {editing && <form className="knowledge-runtime-form" onSubmit={async (event) => { event.preventDefault(); setSaveError(''); try { await onSave(draft); setEditing(false); } catch (reason) { setSaveError(reason instanceof Error ? reason.message : '模型配置保存失败'); } }}>
        <RuntimeFields title="本地向量检索" prefix="embedding" enabled={draft.embedding_enabled} model={draft.embedding_model} baseUrl={draft.embedding_base_url} onEnabled={(value) => edit('embedding_enabled', value)} onModel={(value) => edit('embedding_model', value)} onBaseUrl={(value) => edit('embedding_base_url', value)} />
        <RuntimeFields title="本地自适应语义切分" prefix="semantic_split" enabled={draft.semantic_split_enabled} model={draft.semantic_split_model} baseUrl={draft.semantic_split_base_url} onEnabled={(value) => edit('semantic_split_enabled', value)} onModel={(value) => edit('semantic_split_model', value)} onBaseUrl={(value) => edit('semantic_split_base_url', value)} />
        <RuntimeFields title="知识图谱" prefix="graph" enabled={draft.graph_enabled} model={draft.graph_model} baseUrl={draft.graph_base_url} onEnabled={(value) => edit('graph_enabled', value)} onModel={(value) => edit('graph_model', value)} onBaseUrl={(value) => edit('graph_base_url', value)} />
        <RuntimeFields title="视觉解析" prefix="image" enabled={draft.image_enabled} model={draft.image_model} baseUrl={draft.image_base_url} onEnabled={(value) => edit('image_enabled', value)} onModel={(value) => edit('image_model', value)} onBaseUrl={(value) => edit('image_base_url', value)} />
        <fieldset><legend>重排模型</legend><label className="knowledge-runtime-switch"><input type="checkbox" checked={draft.reranker_enabled} onChange={(event) => edit('reranker_enabled', event.target.checked)} />启用重排</label><label>重排 Provider<select value={draft.reranker_provider} onChange={(event) => edit('reranker_provider', event.target.value as KnowledgeRuntimeConfig['reranker_provider'])}><option value="ollama">Ollama</option><option value="fastembed">本地 FastEmbed</option><option value="api">标准 /rerank API</option><option value="none">停用</option></select></label><label>重排模型<input value={draft.reranker_model} onChange={(event) => edit('reranker_model', event.target.value)} required /></label><label>重排服务地址<input value={draft.reranker_base_url} onChange={(event) => edit('reranker_base_url', event.target.value)} type="url" required /></label>{draft.reranker_provider === 'fastembed' && <small>FastEmbed 在本机使用 ONNX 批量评分；服务地址不会使用，首次运行会下载所选模型。</small>}</fieldset>
        <fieldset><legend>检索多样性</legend><label>相关性权重<input aria-label="MMR 相关性权重" value={draft.mmr_relevance_weight} onChange={(event) => edit('mmr_relevance_weight', Number(event.target.value))} type="number" min="0" max="1" step="0.05" required /></label><small>越高越偏向最高相关结果；越低越优先减少相似切片。</small></fieldset>
        {saveError && <p className="knowledge-runtime-save-error" role="alert">{saveError}</p>}
        <div className="knowledge-runtime-actions"><button type="button" onClick={() => { setDraft(runtime.config); setSaveError(''); setEditing(false); }} disabled={saving}>取消</button><button type="submit" disabled={saving}>{saving ? '正在应用…' : '保存并应用'}</button></div>
      </form>}
    </div>
  </details>;
}

function RuntimeFields({ title, prefix, enabled, model, baseUrl, onEnabled, onModel, onBaseUrl }: { title: string; prefix: 'embedding' | 'semantic_split' | 'graph' | 'image'; enabled: boolean; model: string; baseUrl: string; onEnabled: (value: boolean) => void; onModel: (value: string) => void; onBaseUrl: (value: string) => void }) {
  const label = prefix === 'embedding' ? '向量' : prefix === 'semantic_split' ? '拆分' : prefix === 'graph' ? '图谱' : '视觉';
  return <fieldset><legend>{title}</legend><label className="knowledge-runtime-switch"><input type="checkbox" checked={enabled} onChange={(event) => onEnabled(event.target.checked)} />启用{title}</label><label>{label}模型<input value={model} onChange={(event) => onModel(event.target.value)} required /></label><label>{label}服务地址<input value={baseUrl} onChange={(event) => onBaseUrl(event.target.value)} type="url" required /></label>{prefix === 'semantic_split' && <small>标题结构清晰的文档保持规则切分；仅对超长无结构段落使用本地向量判断主题边界。</small>}</fieldset>;
}
