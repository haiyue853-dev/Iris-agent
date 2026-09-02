import { useCallback, useEffect, useRef, useState } from 'react';
import { Pencil } from 'lucide-react';
import { applyKnowledgeEvaluationRecommendation, auditKnowledgeGraph, createKnowledge, createKnowledgeCollection, deleteKnowledge, deleteKnowledgeCollection, deleteKnowledgeGraphEntity, deleteKnowledgeGraphRelation, evaluateKnowledge, exportKnowledge, generateKnowledgeEvaluation, getKnowledge, getKnowledgeBadCases, getKnowledgeCollectionRetrievalConfig, getKnowledgeDuplicates, getKnowledgeEvaluationCases, getKnowledgeEvaluationGate, getKnowledgeEvaluationHistory, getKnowledgeIndexProgress, getKnowledgeRuntime, getKnowledgeStats, importKnowledgeBackup, knowledgeSourceUrl, listKnowledge, listKnowledgeCollections, mergeKnowledgeGraph, moveKnowledge, recordKnowledgeBadCase, reindexAllKnowledge, reindexKnowledge, renameKnowledgeCollection, renameKnowledgeGraphEntity, replayKnowledgeBadCase, restoreKnowledgeEvaluationConfig, saveKnowledgeEvaluationCases, searchKnowledge, testKnowledgeRuntime, updateKnowledge, updateKnowledgeCollectionRetrievalConfig, updateKnowledgeEvaluationGate, updateKnowledgeGraphRelation, updateKnowledgeRuntime, uploadKnowledge, getKnowledgeGraph, listKnowledgeTopics, summarizeKnowledgeGraph, validateKnowledgeEvaluationCases, type DuplicateSuggestion, type GraphAudit, type GraphSummary, type KnowledgeBadCase, type KnowledgeCollection, type KnowledgeCollectionRetrievalConfig, type KnowledgeEvaluation, type KnowledgeEvaluationCase, type KnowledgeEvaluationCaseValidation, type KnowledgeEvaluationGate, type KnowledgeEvaluationHistoryItem, type KnowledgeIndexProgress, type KnowledgeRuntime, type KnowledgeRuntimeConfig, type KnowledgeRuntimeComponent, type KnowledgeStats } from '../../api/knowledge';
import type { KnowledgeDetail, KnowledgeEntry, KnowledgeSearchHit } from '../../types';
import KnowledgeGraphCanvas from './KnowledgeGraphCanvas';
import DocumentMindMap from './DocumentMindMap';
import RagRuntimePanel from './RagRuntimePanel';
import { getKnowledgeMindMap, type DocumentMindMapData } from '../../api/knowledge';
import { parseEvaluationDataset, serializeEvaluationDataset, type EvaluationDatasetFormat } from './evaluation-dataset';
import { EvaluationCaseManager } from './EvaluationCaseManager';
import { KnowledgeChunkEditor } from './KnowledgeChunkEditor';
import { RetrievalDebugger } from './RetrievalDebugger';

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function parseEvaluationCases(source: string): KnowledgeEvaluationCase[] {
  return source.split('\n').map((item) => item.trim()).filter(Boolean).map((line) => {
    const [question = '', expectedTitle = '', chunkList = ''] = line.split('||').map((item) => item.trim());
    const relevantChunkIds = chunkList.split(',').map((item) => item.trim()).filter(Boolean);
    return { question, ...(expectedTitle ? { expected_title: expectedTitle } : {}),
      ...(relevantChunkIds.length ? { relevant_chunk_ids: relevantChunkIds } : {}) };
  }).filter((item) => item.question);
}

function formatEvaluationCase(item: KnowledgeEvaluationCase | KnowledgeBadCase): string {
  if (item.relevant_chunk_ids?.length) return `${item.question} || ${item.expected_title || ''} || ${item.relevant_chunk_ids.join(',')}`;
  return `${item.question}${item.expected_title ? ` || ${item.expected_title}` : ''}`;
}

function isPreviewableSource(document: KnowledgeDetail): boolean {
  const mediaType = document.media_type || '';
  return mediaType === 'application/pdf' || mediaType.startsWith('image/') || mediaType.startsWith('text/');
}

function sourcePreviewUrl(document: KnowledgeDetail, citationChunkId: string | null): string {
  const url = knowledgeSourceUrl(document.id);
  if (document.media_type !== 'application/pdf' || !citationChunkId) return url;
  const location = document.chunks?.find((chunk) => chunk.id === citationChunkId)?.location;
  const page = location?.match(/第\s*(\d+)\s*页/)?.[1];
  return page ? `${url}#page=${page}` : url;
}

export default function KnowledgePage({ openDocumentId, openChunkId }: { openDocumentId?: string | null; openChunkId?: string | null }) {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [selected, setSelected] = useState<KnowledgeDetail | null>(null);
  const [detailPanelClosed, setDetailPanelClosed] = useState(false);
  const [citationChunkId, setCitationChunkId] = useState<string | null>(null);
  const [knowledgeView, setKnowledgeView] = useState<'mindmap' | 'relations'>('mindmap');
  const [mindMap, setMindMap] = useState<DocumentMindMapData | null>(null);
  const [mindMapEvidence, setMindMapEvidence] = useState<string[]>([]);
  const [error, setError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [question, setQuestion] = useState('');
  const [hits, setHits] = useState<KnowledgeSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [topics, setTopics] = useState<string[]>([]);
  const [collections, setCollections] = useState<KnowledgeCollection[]>([]);
  const [collectionId, setCollectionId] = useState('collection-general');
  const [showCollectionForm, setShowCollectionForm] = useState(false);
  const [collectionName, setCollectionName] = useState('');
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [maintaining, setMaintaining] = useState(false);
  const [deleteCollectionId, setDeleteCollectionId] = useState<string | null>(null);
  const [renameCollectionId, setRenameCollectionId] = useState<string | null>(null);
  const [renameCollectionName, setRenameCollectionName] = useState('');
  const [collectionActionError, setCollectionActionError] = useState('');
  const [retrievalConfigCollectionId, setRetrievalConfigCollectionId] = useState<string | null>(null);
  const [retrievalConfig, setRetrievalConfig] = useState<KnowledgeCollectionRetrievalConfig | null>(null);
  const [retrievalConfigSaving, setRetrievalConfigSaving] = useState(false);
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([]);
  const [bulkDestinationId, setBulkDestinationId] = useState('');
  const [bulkWorking, setBulkWorking] = useState(false);
  const [refiningGraph, setRefiningGraph] = useState(false);
  const [editingDocument, setEditingDocument] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [mergingGraph, setMergingGraph] = useState(false);
  const [retryingFailed, setRetryingFailed] = useState(false);
  const [importingBackup, setImportingBackup] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [runtime, setRuntime] = useState<KnowledgeRuntime | null>(null);
  const [runtimeSaving, setRuntimeSaving] = useState(false);
  const [runtimeTesting, setRuntimeTesting] = useState(false);
  const [indexProgress, setIndexProgress] = useState<Record<string, KnowledgeIndexProgress>>({});
  const [evaluationQuestions, setEvaluationQuestions] = useState('');
  const [evaluationLabelQuestion, setEvaluationLabelQuestion] = useState('');
  const [evaluationLabelCandidates, setEvaluationLabelCandidates] = useState<KnowledgeSearchHit[]>([]);
  const [selectedEvaluationChunkIds, setSelectedEvaluationChunkIds] = useState<string[]>([]);
  const [evaluationLabelQueue, setEvaluationLabelQueue] = useState<string[]>([]);
  const [searchingEvaluationCandidates, setSearchingEvaluationCandidates] = useState(false);
  const [evaluation, setEvaluation] = useState<KnowledgeEvaluation | null>(null);
  const [evaluationCaseValidation, setEvaluationCaseValidation] = useState<KnowledgeEvaluationCaseValidation | null>(null);
  const [validatingEvaluationCases, setValidatingEvaluationCases] = useState(false);
  const [generatedEvaluationCases, setGeneratedEvaluationCases] = useState<Array<{ question: string; expected_title: string; expected_answer?: string }>>([]);
  const [evaluating, setEvaluating] = useState(false);
  const [applyingEvaluationRecommendation, setApplyingEvaluationRecommendation] = useState(false);
  const [generatingEvaluation, setGeneratingEvaluation] = useState(false);
  const [savedEvaluationCount, setSavedEvaluationCount] = useState(0);
  const [evaluationHistory, setEvaluationHistory] = useState<KnowledgeEvaluationHistoryItem[]>([]);
  const [evaluationComparison, setEvaluationComparison] = useState<{ recall_at_1: number; recall_at_3: number; mrr: number } | null>(null);
  const [evaluationGate, setEvaluationGate] = useState<KnowledgeEvaluationGate>({ recall_at_1: 0.7, recall_at_3: 0.8, mrr: 0.75 });
  const [savingEvaluationGate, setSavingEvaluationGate] = useState(false);
  const [badCases, setBadCases] = useState<KnowledgeBadCase[]>([]);
  const [badCaseReasons, setBadCaseReasons] = useState<Record<string, string>>({});
  const [recordingBadCase, setRecordingBadCase] = useState<string | null>(null);
  const [replayingBadCase, setReplayingBadCase] = useState<string | null>(null);
  const [duplicateSuggestions, setDuplicateSuggestions] = useState<DuplicateSuggestion[] | null>(null);
  const [checkingDuplicates, setCheckingDuplicates] = useState(false);
  const [dismissedDuplicates, setDismissedDuplicates] = useState<string[]>([]);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [topic, setTopic] = useState('');
  const [libraryCollapsed, setLibraryCollapsed] = useState(false);
  const [showAdvancedActions, setShowAdvancedActions] = useState(false);
  const advancedActionsRef = useRef<HTMLDivElement | null>(null);
  const [graph, setGraph] = useState<{ nodes: { id: string; label: string; kind: string; document_count: number }[]; edges: { source: string; target: string; relation: string; document_id?: string; confidence?: number; evidence?: string | null; evidence_chunk_id?: string | null }[] }>({ nodes: [], edges: [] });
  const [graphNode, setGraphNode] = useState<string | null>(null);
  const [graphEdge, setGraphEdge] = useState<{ source: string; target: string; relation: string; document_id?: string; confidence?: number; evidence?: string | null } | null>(null);
  const [graphQuery, setGraphQuery] = useState('');
  const [graphKindFilter, setGraphKindFilter] = useState<'all' | 'topic' | 'entity'>('all');
  const [graphConfidence, setGraphConfidence] = useState(0);
  const [graphSummary, setGraphSummary] = useState<GraphSummary | null>(null);
  const [summarizingGraph, setSummarizingGraph] = useState(false);
  const [graphAudit, setGraphAudit] = useState<GraphAudit | null>(null);
  const [auditingGraph, setAuditingGraph] = useState(false);
  const [editingGraphRelation, setEditingGraphRelation] = useState(false);
  const [graphRelationDraft, setGraphRelationDraft] = useState('');
  const [savingGraphRelation, setSavingGraphRelation] = useState(false);
  const [editingGraphEntity, setEditingGraphEntity] = useState(false);
  const [graphEntityDraft, setGraphEntityDraft] = useState('');
  const [confirmingEntityDelete, setConfirmingEntityDelete] = useState(false);
  const [graphZoom, setGraphZoom] = useState(1);
  const [graphPan, setGraphPan] = useState({ x: 0, y: 0 });
  const [nodeOffsets, setNodeOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const [dragging, setDragging] = useState<{ id: string | null; x: number; y: number } | null>(null);
  const graphRef = useRef<SVGSVGElement>(null);
  const sourceChunkRefs = useRef<Record<string, HTMLElement | null>>({});
  const originalSourceUrl = selected ? sourcePreviewUrl(selected, citationChunkId) : '';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await listKnowledge(collectionId || undefined));
      setError(false);
    } catch {
      setError(true);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [collectionId]);
  const loadEvaluationHistory = useCallback(async () => {
    if (!collectionId) { setEvaluationHistory([]); return; }
    try { setEvaluationHistory(await getKnowledgeEvaluationHistory(collectionId)); }
    catch { setEvaluationHistory([]); }
  }, [collectionId]);
  const loadBadCases = useCallback(async () => {
    try { setBadCases((await getKnowledgeBadCases()).filter((item) => item.collection_id === collectionId)); }
    catch { setBadCases([]); }
  }, [collectionId]);
  const loadEvaluationGate = useCallback(async () => {
    if (!collectionId) return;
    try { const gate = await getKnowledgeEvaluationGate(collectionId); if (gate && Number.isFinite(gate.recall_at_1) && Number.isFinite(gate.recall_at_3) && Number.isFinite(gate.mrr)) setEvaluationGate(gate); } catch {}
  }, [collectionId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setSelectedEntryIds((ids) => ids.filter((id) => entries.some((entry) => entry.id === id))); }, [entries]);
  useEffect(() => {
    if (!entries.some((entry) => entry.status === 'queued' || entry.status === 'indexing')) return;
    const timer = window.setInterval(() => void load(), 1500);
    return () => window.clearInterval(timer);
  }, [entries, load]);
  useEffect(() => { void listKnowledgeCollections().then(setCollections).catch(() => setCollections([])); }, []);
  useEffect(() => { void listKnowledgeTopics(collectionId || undefined).then(setTopics).catch(() => setTopics([])); }, [collectionId, entries.length]);
  useEffect(() => { void getKnowledgeStats(collectionId || undefined).then(setStats).catch(() => setStats(null)); }, [collectionId, entries.length]);
  useEffect(() => {
    void getKnowledgeRuntime().then((value) => { if (value?.config && Array.isArray(value.components)) setRuntime(value); }).catch(() => setRuntime(null));
  }, []);
  const loadIndexProgress = useCallback(() => {
    void getKnowledgeIndexProgress().then((items) => setIndexProgress(Object.fromEntries(items.map((item) => [item.document_id, item])))).catch(() => setIndexProgress({}));
  }, []);
  useEffect(() => { loadIndexProgress(); }, [loadIndexProgress, entries.length]);
  useEffect(() => {
    if (!entries.some((entry) => entry.status === 'queued' || entry.status === 'indexing')) return;
    const timer = window.setInterval(loadIndexProgress, 1200);
    return () => window.clearInterval(timer);
  }, [entries, loadIndexProgress]);
  useEffect(() => { const key = collectionId || 'all'; const saved = localStorage.getItem(`iris_knowledge_eval_${key}`) || ''; setEvaluationQuestions(saved); setSavedEvaluationCount(saved.split('\n').filter(Boolean).length); try { setDismissedDuplicates(JSON.parse(localStorage.getItem(`iris_knowledge_duplicate_dismissed_${key}`) || '[]')); } catch { setDismissedDuplicates([]); } setEvaluation(null); setEvaluationCaseValidation(null); setEvaluationComparison(null); void loadEvaluationHistory(); void loadBadCases(); void loadEvaluationGate(); void getKnowledgeEvaluationCases(collectionId || undefined).then((cases) => { if (!cases.length) return; const text = cases.map(formatEvaluationCase).join('\n'); setEvaluationQuestions(text); setSavedEvaluationCount(cases.length); localStorage.setItem(`iris_knowledge_eval_${key}`, text); }).catch(() => undefined); }, [collectionId, loadBadCases, loadEvaluationGate, loadEvaluationHistory]);
  useEffect(() => { void getKnowledgeGraph(topic || undefined, collectionId || undefined).then(setGraph).catch(() => setGraph({ nodes: [], edges: [] })); }, [topic, collectionId, entries.length]);
  useEffect(() => {
    if (!renameCollectionId && !deleteCollectionId && !retrievalConfigCollectionId) return;
    const closeCollectionMenu = (event: PointerEvent) => {
      if (!(event.target instanceof Element) || event.target.closest('.knowledge-collection-confirm, .knowledge-collection-retrieval, .knowledge-collection-rename, .knowledge-collection-delete, .knowledge-collection-strategy')) return;
      setRenameCollectionId(null);
      setDeleteCollectionId(null);
      setRetrievalConfigCollectionId(null);
      setCollectionActionError('');
    };
    document.addEventListener('pointerdown', closeCollectionMenu);
    return () => document.removeEventListener('pointerdown', closeCollectionMenu);
  }, [deleteCollectionId, renameCollectionId, retrievalConfigCollectionId]);
  useEffect(() => {
    if (!showAdvancedActions) return;
    const closeAdvancedActions = (event: PointerEvent) => {
      if (!(event.target instanceof Node) || !advancedActionsRef.current?.contains(event.target)) setShowAdvancedActions(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setShowAdvancedActions(false); };
    document.addEventListener('pointerdown', closeAdvancedActions);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeAdvancedActions);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [showAdvancedActions]);

  const openDetail = async (id: string, citedChunkId: string | null = null) => {
    try {
      const detail = await getKnowledge(id);
      setSelected(detail);
      setDetailPanelClosed(false);
      setCitationChunkId(citedChunkId);
      setKnowledgeView('mindmap');
      setMindMapEvidence([]);
      setMindMap(null);
      void getKnowledgeMindMap(id).then(setMindMap).catch(() => setMindMap(null));
      setError(false);
    } catch {
      setError(true);
    }
  };
  useEffect(() => { if (openDocumentId) void openDetail(openDocumentId, openChunkId || null); }, [openDocumentId, openChunkId]);
  useEffect(() => {
    if (!citationChunkId || !selected?.chunks?.some((chunk) => chunk.id === citationChunkId)) return;
    sourceChunkRefs.current[citationChunkId]?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
  }, [citationChunkId, selected]);

  const add = async () => {
    const t = title.trim();
    const c = content.trim();
    if (!t || !c) return;
    try {
      const created = await createKnowledge({
        title: t,
        content: c,
        category: category.trim() || undefined,
        sourceUrl: sourceUrl.trim() || undefined,
        collectionId: collectionId || 'collection-general',
      });
      setTitle('');
      setContent('');
      setSourceUrl('');
      setEntries((prev) => [created, ...prev]);
      setError(false);
    } catch {
      setError(true);
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteKnowledge(id);
      setEntries((prev) => prev.filter((entry) => entry.id !== id));
      if (selected?.id === id) {
        setSelected(null);
        setDetailPanelClosed(false);
      }
    } catch {
      setError(true);
    }
  };
  const toggleEntry = (id: string) => setSelectedEntryIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]);
  const runBulk = async (action: 'delete' | 'reindex' | 'move') => {
    if (!selectedEntryIds.length || (action === 'move' && !bulkDestinationId)) return;
    setBulkWorking(true);
    try {
      if (action === 'delete') await Promise.all(selectedEntryIds.map((id) => deleteKnowledge(id)));
      if (action === 'reindex') await Promise.all(selectedEntryIds.map((id) => reindexKnowledge(id)));
      if (action === 'move') await Promise.all(selectedEntryIds.map((id) => moveKnowledge(id, bulkDestinationId)));
      setSelectedEntryIds([]); setSelected(null); setDetailPanelClosed(false); setError(false); await load();
    } catch { setError(true); } finally { setBulkWorking(false); }
  };
  const reindex = async (vectorsOnly: boolean) => {
    if (!selected) return;
    setMaintaining(true);
    try {
      const queued = await reindexKnowledge(selected.id, vectorsOnly);
      setSelected({ ...selected, ...queued });
      setEntries((items) => items.map((item) => item.id === queued.id ? { ...item, ...queued } : item));
      setError(false);
    } catch { setError(true); } finally { setMaintaining(false); }
  };
  const beginEdit = () => { if (!selected) return; setEditTitle(selected.title); setEditContent(selected.content || selected.chunks?.map((item) => item.content).join('\n\n') || ''); setEditingDocument(true); };
  const saveEdit = async () => {
    if (!selected || !editTitle.trim() || !editContent.trim()) return;
    try { const updated = await updateKnowledge(selected.id, editTitle.trim(), editContent.trim()); setSelected({ ...selected, ...updated, content: editContent.trim() }); setEntries((items) => items.map((item) => item.id === updated.id ? { ...item, ...updated } : item)); setEditingDocument(false); setError(false); }
    catch { setError(true); }
  };
  const exportCurrentKnowledge = async () => {
    setExporting(true);
    try { const data = await exportKnowledge(collectionId || undefined); const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `iris-knowledge-${collectionId || 'all'}-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(url); setNotice('知识库备份已开始下载。'); setError(false); setErrorMessage(''); }
    catch { setError(true); } finally { setExporting(false); }
  };
  const mergeGraphEntities = async () => {
    setMergingGraph(true);
    try { const result = await mergeKnowledgeGraph(collectionId || undefined); await getKnowledgeGraph(topic || undefined, collectionId || undefined).then(setGraph); setNotice(result.merged ? `已合并 ${result.merged} 个同义实体。` : '未发现可安全合并的同义实体。'); setError(false); setErrorMessage(''); }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '图谱合并失败'); } finally { setMergingGraph(false); }
  };
  const retryFailedDocuments = async () => {
    const failed = entries.filter((entry) => entry.status === 'failed');
    if (!failed.length) return;
    setRetryingFailed(true);
    try { await Promise.all(failed.map((entry) => reindexKnowledge(entry.id))); setNotice(`已将 ${failed.length} 份失败资料重新加入索引队列。`); setError(false); setErrorMessage(''); await load(); }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '重新索引失败'); } finally { setRetryingFailed(false); }
  };
  const restoreBackup = async (file: File | undefined) => {
    if (!file || !collectionId) return;
    setImportingBackup(true);
    try { const result = await importKnowledgeBackup(file, collectionId); setNotice(result.imported ? `已导入 ${result.imported} 份资料，正在后台建立索引。` : '备份中没有可导入的资料。'); setError(false); setErrorMessage(''); await load(); }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '恢复备份失败'); } finally { setImportingBackup(false); }
  };
  const runEvaluation = async () => {
    const cases = parseEvaluationCases(evaluationQuestions).map((item) => { const generated = generatedEvaluationCases.find((candidate) => candidate.question === item.question && candidate.expected_title === item.expected_title); return { ...item, ...(generated?.expected_answer ? { expected_answer: generated.expected_answer } : {}) }; });
    if (!cases.length) return;
    setEvaluating(true);
    try { const result = await evaluateKnowledge(cases, collectionId || undefined); const previous = evaluationHistory[0]; const delta = previous && previous.total === result.total ? result.hit_count - previous.hit_count : 0; setEvaluationComparison(previous ? { recall_at_1: (result.recall_at_1 || 0) - (previous.recall_at_1 || 0), recall_at_3: (result.recall_at_3 || 0) - (previous.recall_at_3 || 0), mrr: (result.mrr || 0) - (previous.mrr || 0) } : null); setEvaluation(result); await loadEvaluationHistory(); setNotice(result.judged_total ? `评测完成：Hit@3 ${(result.hit_at_3 ?? result.recall_at_3 ?? 0) * 100}% · MRR ${result.mrr || 0}。` : `评测完成：${result.hit_count}/${result.total} 个问题有资料命中。${delta ? `较上次${delta > 0 ? '提升' : '下降'} ${Math.abs(delta)} 题。` : ''}`); setError(false); setErrorMessage(''); return result; }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '评测失败'); } finally { setEvaluating(false); }
  };
  const updateSelectedChunk = (updated: { id: string; content: string; location?: string | null }) => {
    setSelected((current) => current ? { ...current, chunks: current.chunks?.map((chunk) => chunk.id === updated.id ? { ...chunk, ...updated } : chunk) } : current);
    setNotice('切片已更新，检索索引已同步。');
    setError(false);
    setErrorMessage('');
  };
  const searchEvaluationCandidates = async (questionOverride?: string) => {
    const query = (questionOverride ?? evaluationLabelQuestion).trim();
    if (!query) return;
    setSearchingEvaluationCandidates(true);
    try {
      const candidates = (await searchKnowledge(query, 10, collectionId || undefined)).filter((item) => item.chunk_id);
      setEvaluationLabelCandidates(candidates);
      setSelectedEvaluationChunkIds([]);
      setNotice(candidates.length ? `找到 ${candidates.length} 个候选切片，请勾选所有正确证据。` : '没有找到可标注的候选切片。');
      setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '检索候选切片失败'); }
    finally { setSearchingEvaluationCandidates(false); }
  };
  const addLabeledEvaluationCase = () => {
    const question = evaluationLabelQuestion.trim();
    const selected = evaluationLabelCandidates.filter((item) => item.chunk_id && selectedEvaluationChunkIds.includes(item.chunk_id));
    if (!question || !selected.length) return;
    const labeledCase: KnowledgeEvaluationCase = {
      question,
      expected_title: selected[0].title,
      relevant_chunk_ids: [...new Set(selected.map((item) => item.chunk_id as string))],
    };
    const existing = parseEvaluationCases(evaluationQuestions).filter((item) => item.question !== question);
    const updated = [...existing, labeledCase];
    const text = updated.map(formatEvaluationCase).join('\n');
    setEvaluationQuestions(text);
    setEvaluationCaseValidation(null);
    setSavedEvaluationCount(updated.length);
    setNotice(`已标注“${question}”，请选择“保存为回归问题”持久化评测集。`);
    const [nextQuestion, ...remainingQuestions] = evaluationLabelQueue;
    if (nextQuestion) {
      setEvaluationLabelQueue(remainingQuestions);
      setEvaluationLabelQuestion(nextQuestion);
      void searchEvaluationCandidates(nextQuestion);
    }
  };
  const updateManagedEvaluationCases = (cases: KnowledgeEvaluationCase[]) => {
    const text = cases.filter((item) => item.question.trim()).map(formatEvaluationCase).join('\n');
    setEvaluationQuestions(text);
    setSavedEvaluationCount(cases.length);
    setEvaluationCaseValidation(null);
  };
  const validateManagedEvaluationCases = async () => {
    const cases = parseEvaluationCases(evaluationQuestions);
    if (!cases.length) return;
    setValidatingEvaluationCases(true);
    try {
      const result = await validateKnowledgeEvaluationCases(cases, collectionId || undefined);
      setEvaluationCaseValidation(result);
      setNotice(`评测集检查完成：重复 ${result.summary.duplicates}，空标注 ${result.summary.empty_annotations}，失效切片 ${result.summary.invalid_chunks}。`);
      setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '检查评测集失败'); }
    finally { setValidatingEvaluationCases(false); }
  };
  const startManagedCaseLabeling = (question: string) => {
    setEvaluationLabelQueue([]);
    setEvaluationLabelQuestion(question);
    void searchEvaluationCandidates(question);
  };
  const startManagedCaseLabelingQueue = (questions: string[]) => {
    const [firstQuestion, ...remainingQuestions] = questions;
    if (!firstQuestion) return;
    setEvaluationLabelQueue(remainingQuestions);
    setEvaluationLabelQuestion(firstQuestion);
    void searchEvaluationCandidates(firstQuestion);
  };
  const importEvaluationDataset = async (file: File | undefined) => {
    if (!file) return;
    try {
      const cases = parseEvaluationDataset(await file.text(), file.name);
      const text = cases.map(formatEvaluationCase).join('\n');
      setEvaluationQuestions(text);
      setSavedEvaluationCount(cases.length);
      setEvaluation(null);
      setEvaluationCaseValidation(null);
      setNotice(`已导入 ${cases.length} 条评测用例。`);
      setError(false); setErrorMessage('');
    } catch (reason) {
      setError(true);
      setErrorMessage(reason instanceof Error ? reason.message : '导入评测集失败');
    }
  };
  const exportEvaluationDataset = (format: EvaluationDatasetFormat) => {
    const cases = parseEvaluationCases(evaluationQuestions);
    if (!cases.length) { setError(true); setErrorMessage('评测集没有有效问题'); return; }
    const content = serializeEvaluationDataset(cases, format);
    const blob = new Blob([format === 'csv' ? `\uFEFF${content}` : content], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `iris-rag-evaluation-${collectionId || 'all'}.${format}`;
    link.click();
    URL.revokeObjectURL(url);
    setNotice(`已导出 ${format.toUpperCase()} 评测集。`);
    setError(false); setErrorMessage('');
  };
  const applyEvaluationRecommendation = async (recommendation: NonNullable<KnowledgeEvaluation['recommendations']>[number]) => {
    if (!collectionId) return;
    setApplyingEvaluationRecommendation(true);
    try {
      const previousConfig = await getKnowledgeCollectionRetrievalConfig(collectionId);
      await applyKnowledgeEvaluationRecommendation(collectionId, recommendation);
      const result = await runEvaluation();
      if (result?.quality_gate?.passed === false) {
        await updateKnowledgeCollectionRetrievalConfig(collectionId, previousConfig);
        await runEvaluation();
        setNotice('评测建议未通过回归门禁，已自动恢复原检索策略。');
        return;
      }
      setNotice(`已应用${recommendation.field === 'candidate_multiplier' ? '候选倍数' : 'MMR 相关性权重'}建议，并完成重新评测。`);
      setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '应用评测建议失败'); }
    finally { setApplyingEvaluationRecommendation(false); }
  };
  const restoreEvaluationConfig = async (historyItem: KnowledgeEvaluationHistoryItem) => {
    if (!collectionId) return;
    setApplyingEvaluationRecommendation(true);
    try {
      await restoreKnowledgeEvaluationConfig(collectionId, historyItem.id);
      await loadEvaluationHistory();
      if (evaluationQuestions.trim()) await runEvaluation();
      setNotice('已回退到该次评测的检索策略。');
      setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '回退检索策略失败'); }
    finally { setApplyingEvaluationRecommendation(false); }
  };
  const saveEvaluationBadCase = async (result: KnowledgeEvaluation['results'][number]) => {
    if (!collectionId) return;
    setRecordingBadCase(result.question);
    try {
      const saved = await recordKnowledgeBadCase({ question: result.question, collection_id: collectionId, expected_title: result.expected_title || null, relevant_chunk_ids: result.relevant_chunk_ids || [], relevant_document_ids: result.relevant_document_ids || [], expected_answer: result.expected_answer || '', actual_answer: result.hits[0]?.excerpt || '', reason: badCaseReasons[result.question] || '' });
      setBadCases((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
      setNotice('已加入 Bad Case，可在下方随时重放。'); setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '保存 Bad Case 失败'); }
    finally { setRecordingBadCase(null); }
  };
  const replayBadCase = async (badCase: KnowledgeBadCase) => {
    if (!badCase.id) return;
    setReplayingBadCase(badCase.id);
    try {
      const replayed = await replayKnowledgeBadCase(badCase.id);
      const previous = evaluationHistory[0]; setEvaluationComparison(previous ? { recall_at_1: (replayed.evaluation.recall_at_1 || 0) - (previous.recall_at_1 || 0), recall_at_3: (replayed.evaluation.recall_at_3 || 0) - (previous.recall_at_3 || 0), mrr: (replayed.evaluation.mrr || 0) - (previous.mrr || 0) } : null); setEvaluation(replayed.evaluation); await loadEvaluationHistory();
      setNotice(`已重放 Bad Case：${badCase.question}`); setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '重放 Bad Case 失败'); }
    finally { setReplayingBadCase(null); }
  };
  const mergeBadCasesIntoEvaluation = async () => {
    const currentLines = evaluationQuestions.split('\n').map((item) => item.trim()).filter(Boolean);
    const existing = new Set(currentLines.map((item) => item.toLowerCase()));
    const additions = badCases.map(formatEvaluationCase).filter((item) => !existing.has(item.toLowerCase()));
    if (!additions.length) { setNotice('当前回归问题已包含全部 Bad Case。'); return; }
    const merged = [...currentLines, ...additions].join('\n');
    const cases = parseEvaluationCases([...currentLines, ...additions].join('\n'));
    setEvaluationQuestions(merged); setSavedEvaluationCount(cases.length); localStorage.setItem(`iris_knowledge_eval_${collectionId || 'all'}`, merged);
    try { await saveKnowledgeEvaluationCases(cases, collectionId || undefined); setNotice(`已将 ${additions.length} 个 Bad Case 合并到回归问题。`); setError(false); setErrorMessage(''); }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '保存合并后的回归问题失败'); }
  };
  const replayAllBadCases = async () => {
    if (!collectionId || !badCases.length) return;
    const cases = badCases.map((item) => ({ question: item.question, ...(item.expected_title ? { expected_title: item.expected_title } : {}), ...(item.relevant_chunk_ids?.length ? { relevant_chunk_ids: item.relevant_chunk_ids } : {}), ...(item.relevant_document_ids?.length ? { relevant_document_ids: item.relevant_document_ids } : {}), ...(item.expected_answer ? { expected_answer: item.expected_answer } : {}) }));
    setEvaluating(true);
    try {
      const result = await evaluateKnowledge(cases, collectionId); const previous = evaluationHistory[0];
      setEvaluationComparison(previous ? { recall_at_1: (result.recall_at_1 || 0) - (previous.recall_at_1 || 0), recall_at_3: (result.recall_at_3 || 0) - (previous.recall_at_3 || 0), mrr: (result.mrr || 0) - (previous.mrr || 0) } : null); setEvaluation(result); await loadEvaluationHistory();
      setNotice(`已完成 ${cases.length} 个 Bad Case 的批量回归评测。`); setError(false); setErrorMessage('');
    } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '批量重放 Bad Case 失败'); }
    finally { setEvaluating(false); }
  };
  const saveEvaluationGate = async () => {
    if (!collectionId) return;
    setSavingEvaluationGate(true);
    try { setEvaluationGate(await updateKnowledgeEvaluationGate(collectionId, evaluationGate)); setNotice('评测门禁阈值已保存。'); setError(false); setErrorMessage(''); }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '保存评测门禁失败'); }
    finally { setSavingEvaluationGate(false); }
  };
  const generateEvaluationSuite = async () => { setGeneratingEvaluation(true); try { const result = await generateKnowledgeEvaluation(collectionId || undefined); const text = result.cases.map((item) => `${item.question} || ${item.expected_title}`).join('\n'); setGeneratedEvaluationCases(result.cases); setEvaluationQuestions(text); setEvaluation(null); setNotice(result.cases.length ? `已生成 ${result.cases.length} 条${result.generated_by === 'ollama' ? '基于资料' : '基础'}评测用例，请保存或直接运行。` : '没有可用于生成评测的已就绪资料。'); setError(false); setErrorMessage(''); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '自动生成评测失败'); } finally { setGeneratingEvaluation(false); } };
  const checkDuplicates = async () => { setCheckingDuplicates(true); try { const suggestions = await getKnowledgeDuplicates(collectionId || undefined); setDuplicateSuggestions(suggestions); setNotice(suggestions.length ? `发现 ${suggestions.length} 组可能重复资料。` : '未发现高可信重复资料。'); setError(false); setErrorMessage(''); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '重复检测失败'); } finally { setCheckingDuplicates(false); } };
  const dismissDuplicate = (key: string) => { const next = [...new Set([...dismissedDuplicates, key])]; setDismissedDuplicates(next); localStorage.setItem(`iris_knowledge_duplicate_dismissed_${collectionId || 'all'}`, JSON.stringify(next)); };
  const saveEvaluationSuite = async () => { const cases = parseEvaluationCases(evaluationQuestions); const key = collectionId || 'all'; localStorage.setItem(`iris_knowledge_eval_${key}`, evaluationQuestions.trim()); setSavedEvaluationCount(cases.length); if (!cases.length) { setNotice('已清空该知识库的本地回归问题。'); return; } try { await saveKnowledgeEvaluationCases(cases, collectionId || undefined); setNotice(`已保存 ${cases.length} 个回归问题，可跨设备复用。`); setError(false); setErrorMessage(''); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '保存评测集失败'); } };
  const refineGraph = async () => {
    setRefiningGraph(true);
    try { const result = await reindexAllKnowledge(collectionId || undefined); setNotice(result.queued ? `已将 ${result.queued} 份资料加入图谱优化队列。` : '当前知识库没有可优化的资料。'); setError(false); setErrorMessage(''); await load(); }
    catch { setError(true); } finally { setRefiningGraph(false); }
  };

  const saveRuntime = async (config: KnowledgeRuntimeConfig) => {
    setRuntimeSaving(true);
    try {
      const updated = await updateKnowledgeRuntime(config);
      setRuntime(updated);
      setNotice(updated.requires_reindex ? '模型配置已应用。向量配置发生变化，请对现有资料执行重新索引。' : '模型配置已保存并立即应用。');
      setError(false); setErrorMessage('');
    } catch (reason) {
      setError(true); setErrorMessage(reason instanceof Error ? reason.message : '模型配置保存失败');
      throw reason;
    } finally { setRuntimeSaving(false); }
  };
  const testRuntime = async (component?: KnowledgeRuntimeComponent['key']) => {
    setRuntimeTesting(true);
    try {
      const result = await testKnowledgeRuntime(component);
      setRuntime((current) => current ? { ...current, components: current.components.map((item) => result.components.find((tested) => tested.key === item.key) || item) } : current);
      setError(false); setErrorMessage('');
    } catch (reason) {
      setError(true); setErrorMessage(reason instanceof Error ? reason.message : '模型连接测试失败');
    } finally { setRuntimeTesting(false); }
  };

  const ask = async () => {
    const q = question.trim();
    if (!q) return;
    setSearching(true);
    try {
      setHits(await searchKnowledge(q, undefined, collectionId || undefined));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setSearching(false);
    }
  };
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try { const document = await uploadKnowledge(file, '', collectionId || 'collection-general'); setEntries((prev) => [document, ...prev]); setError(false); }
    catch { setError(true); } finally { setUploading(false); }
  };
  const selectCollection = (id: string) => {
    setCollectionId(id);
    setTopic('');
    setSelected(null);
    setCitationChunkId(null);
    setMindMap(null);
    setMindMapEvidence([]);
    setSelectedEntryIds([]);
    setGraphNode(null);
    setGraphEdge(null);
    setGraphSummary(null);
    setGraphAudit(null);
    setHits([]);
  };
  const addCollection = async () => {
    const name = collectionName.trim();
    if (!name) return;
    setCreatingCollection(true);
    try {
      const created = await createKnowledgeCollection(name);
      setCollections((previous) => [...previous, created]);
      selectCollection(created.id); setCollectionName(''); setShowCollectionForm(false); setError(false);
    } catch { setError(true); } finally { setCreatingCollection(false); }
  };
  const removeCollection = async (id: string) => {
    try {
      await deleteKnowledgeCollection(id);
      const remaining = collections.filter((item) => item.id !== id);
      setCollections(remaining);
      if (collectionId === id) { setCollectionId(remaining[0]?.id || ''); setTopic(''); }
      setEntries((items) => collectionId === id ? [] : items);
      setSelected(null); setDeleteCollectionId(null); setCollectionActionError(''); setError(false);
    } catch (reason) { setCollectionActionError(reason instanceof Error ? reason.message : '删除知识库失败'); }
  };
  const renameCollection = async () => {
    if (!renameCollectionId || !renameCollectionName.trim()) return;
    try {
      const renamed = await renameKnowledgeCollection(renameCollectionId, renameCollectionName.trim());
      setCollections((items) => items.map((item) => item.id === renamed.id ? renamed : item));
      setRenameCollectionId(null); setRenameCollectionName(''); setCollectionActionError('');
    } catch (reason) { setCollectionActionError(reason instanceof Error ? reason.message : '重命名知识库失败'); }
  };
  const openCollectionRetrievalConfig = async (id: string) => {
    setRetrievalConfigCollectionId(id); setRetrievalConfig(null); setCollectionActionError('');
    try { setRetrievalConfig(await getKnowledgeCollectionRetrievalConfig(id)); }
    catch (reason) { setCollectionActionError(reason instanceof Error ? reason.message : '读取检索策略失败'); }
  };
  const saveCollectionRetrievalConfig = async () => {
    if (!retrievalConfigCollectionId || !retrievalConfig) return;
    setRetrievalConfigSaving(true);
    try {
      const saved = await updateKnowledgeCollectionRetrievalConfig(retrievalConfigCollectionId, retrievalConfig);
      setRetrievalConfig(saved); setRetrievalConfigCollectionId(null); setNotice('当前知识库的检索策略已保存。'); setCollectionActionError(''); setError(false);
    } catch (reason) { setCollectionActionError(reason instanceof Error ? reason.message : '保存检索策略失败'); }
    finally { setRetrievalConfigSaving(false); }
  };
  const graphNodes = graph.nodes.slice(0, 24);
  const graphPosition = new Map(graphNodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(graphNodes.length, 1) - Math.PI / 2;
    const radius = node.kind === 'topic' ? 0 : 155 + (index % 3) * 22;
    return [node.id, { x: 260 + Math.cos(angle) * radius, y: 205 + Math.sin(angle) * radius }] as const;
  }));
  const activeGraphNode = graph.nodes.find((node) => node.id === graphNode);
  const graphLabel = (id: string) => graph.nodes.find((node) => node.id === id)?.label || id;
  const summarizeSelectedGraph = async () => {
    if (!graphNode && !graphEdge) return;
    setSummarizingGraph(true); setGraphSummary(null);
    try { const result = graphEdge ? await summarizeKnowledgeGraph({ kind: 'relation', source_id: graphEdge.source, target_id: graphEdge.target, relation: graphEdge.relation, document_id: graphEdge.document_id, collection_id: collectionId || undefined }) : await summarizeKnowledgeGraph({ kind: 'entity', node_id: graphNode!, collection_id: collectionId || undefined }); setGraphSummary(result); setError(false); setErrorMessage(''); }
    catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '图谱摘要生成失败'); } finally { setSummarizingGraph(false); }
  };
  const runGraphAudit = async () => { setAuditingGraph(true); try { const result = await auditKnowledgeGraph(collectionId || undefined); setGraphAudit(result); setNotice(`图谱检查完成：${result.counts.low_confidence} 条低置信度、${result.counts.missing_evidence} 条缺少证据、${result.counts.similar_labels} 组相似实体。`); setError(false); setErrorMessage(''); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '图谱检查失败'); } finally { setAuditingGraph(false); } };
  const refreshGraph = async () => { const result = await getKnowledgeGraph(topic || undefined, collectionId || undefined); setGraph(result); };
  const saveGraphRelation = async () => { if (!graphEdge || !graphRelationDraft.trim()) return; setSavingGraphRelation(true); try { const result = await updateKnowledgeGraphRelation({ source_id: graphEdge.source, target_id: graphEdge.target, relation: graphEdge.relation, document_id: graphEdge.document_id, new_relation: graphRelationDraft.trim() }); await refreshGraph(); setNotice(result.updated ? '图谱关系已修改。' : '未找到可修改的图谱关系。'); setEditingGraphRelation(false); setGraphEdge(null); setError(false); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '修改图谱关系失败'); } finally { setSavingGraphRelation(false); } };
  const removeGraphRelation = async () => { if (!graphEdge) return; setSavingGraphRelation(true); try { const result = await deleteKnowledgeGraphRelation({ source_id: graphEdge.source, target_id: graphEdge.target, relation: graphEdge.relation, document_id: graphEdge.document_id }); await refreshGraph(); setNotice(result.deleted ? '错误图谱关系已删除。' : '未找到可删除的图谱关系。'); setGraphEdge(null); setGraphSummary(null); setError(false); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '删除图谱关系失败'); } finally { setSavingGraphRelation(false); } };
  const saveGraphEntity = async () => { if (!graphNode || !collectionId || !graphEntityDraft.trim()) return; setSavingGraphRelation(true); try { const result = await renameKnowledgeGraphEntity(graphNode, graphEntityDraft.trim(), collectionId); await refreshGraph(); setNotice(result.updated ? '实体已在当前知识库中重命名。' : '未找到可修改的实体关系。'); setGraphNode(null); setGraphSummary(null); setEditingGraphEntity(false); setError(false); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '修改实体失败'); } finally { setSavingGraphRelation(false); } };
  const removeGraphEntity = async () => { if (!graphNode || !collectionId) return; setSavingGraphRelation(true); try { const result = await deleteKnowledgeGraphEntity(graphNode, collectionId); await refreshGraph(); setNotice(result.deleted ? `已删除该实体在当前知识库中的 ${result.deleted} 条关系。` : '未找到可删除的实体关系。'); setGraphNode(null); setGraphSummary(null); setConfirmingEntityDelete(false); setError(false); } catch (reason) { setError(true); setErrorMessage(reason instanceof Error ? reason.message : '删除实体失败'); } finally { setSavingGraphRelation(false); } };
  const filteredGraphNodes = graph.nodes.filter((node) => graphKindFilter === 'all' || (graphKindFilter === 'topic' ? node.kind === 'topic' : node.kind !== 'topic'));
  const filteredNodeIds = new Set(filteredGraphNodes.map((node) => node.id));
  const filteredGraphEdges = graph.edges.filter((edge) => filteredNodeIds.has(edge.source) && filteredNodeIds.has(edge.target) && (edge.confidence ?? 0) >= graphConfidence);
  const graphPointer = (event: React.PointerEvent<SVGElement>) => {
    const box = graphRef.current?.getBoundingClientRect();
    return box ? { x: (event.clientX - box.left) * 520 / box.width / graphZoom, y: (event.clientY - box.top) * 410 / box.height / graphZoom } : { x: 0, y: 0 };
  };
  const graphMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!dragging) return;
    const point = graphPointer(event); const dx = point.x - dragging.x; const dy = point.y - dragging.y;
    if (dragging.id) setNodeOffsets((current) => ({ ...current, [dragging.id!]: { x: (current[dragging.id!]?.x || 0) + dx, y: (current[dragging.id!]?.y || 0) + dy } }));
    else setGraphPan((current) => ({ x: current.x + dx, y: current.y + dy }));
    setDragging({ ...dragging, ...point });
  };

  return (
    <section className="knowledge-page" aria-label="知识库">
      <header className="knowledge-header">
        <div className="knowledge-breadcrumb" aria-label="知识库路径"><span>知识库</span><b>›</b><strong>{selected?.title || '全部资料'}</strong><span className="knowledge-breadcrumb-view">{knowledgeView === 'relations' ? '图谱' : '文档'}</span></div>
        <div><span>LOCAL KNOWLEDGE</span><h1>知识库</h1><p>归档、检索并连接你的本地资料。</p></div>
        <div className="knowledge-header-actions">
          <div className="knowledge-more-menu" ref={advancedActionsRef}>
            <button type="button" className="knowledge-more-toggle" aria-expanded={showAdvancedActions} aria-label="更多操作" onClick={() => setShowAdvancedActions((value) => !value)}>更多 <span aria-hidden="true">⌄</span></button>
            {showAdvancedActions && <div className="knowledge-advanced-actions" role="menu" onClick={() => setShowAdvancedActions(false)}>
              <button className="knowledge-refine-graph" onClick={() => void exportCurrentKnowledge()} disabled={exporting}>{exporting ? '正在导出…' : '导出备份'}</button>
              <label className="knowledge-refine-graph">{importingBackup ? '正在恢复…' : '恢复备份'}<input type="file" accept="application/json,.json" onChange={(event) => void restoreBackup(event.target.files?.[0])} disabled={importingBackup || !collectionId} /></label>
              {entries.some((entry) => entry.status === 'failed') && <button className="knowledge-refine-graph" onClick={() => void retryFailedDocuments()} disabled={retryingFailed}>{retryingFailed ? '正在重试…' : '重试失败资料'}</button>}
              <button className="knowledge-refine-graph" onClick={() => void runGraphAudit()} disabled={auditingGraph || !graph.nodes.length}>{auditingGraph ? '正在检查…' : '检查图谱质量'}</button>
              <button className="knowledge-refine-graph" onClick={() => void mergeGraphEntities()} disabled={mergingGraph || !graph.nodes.length}>{mergingGraph ? '正在合并…' : '合并同义实体'}</button>
              <button className="knowledge-refine-graph" onClick={() => void refineGraph()} disabled={refiningGraph || !entries.length}>{refiningGraph ? '正在优化图谱…' : '优化图谱'}</button>
            </div>}
          </div>
        </div>
      </header>

      {error && <div className="knowledge-error" role="alert">{errorMessage || '知识库服务暂不可用。'}</div>}
      {notice && <div className="knowledge-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="关闭提示">×</button></div>}
      {stats && <div className="knowledge-health"><span><b>{stats.documents}</b> 资料</span><span><b>{stats.chunks}</b> 切片</span><span><b>{stats.nodes}</b> 节点</span><span><b>{stats.edges}</b> 关系</span><span className={stats.failed ? 'warning' : ''}><b>{stats.failed ? `${stats.failed} 失败` : `${stats.ready} 就绪`}</b>{stats.indexing ? ` · ${stats.indexing} 索引中` : ''}</span></div>}
      <details className="knowledge-management"><summary>管理与评测</summary><div className="knowledge-management-body">
      {runtime && <RagRuntimePanel runtime={runtime} saving={runtimeSaving} testing={runtimeTesting} onSave={saveRuntime} onTest={testRuntime} />}
      <RetrievalDebugger collectionId={collectionId || undefined} onOpenSource={(documentId, chunkId) => void openDetail(documentId, chunkId)} />
      <EvaluationCaseManager cases={parseEvaluationCases(evaluationQuestions)} validation={evaluationCaseValidation} onChange={updateManagedEvaluationCases} onLabel={startManagedCaseLabeling} onLabelMany={startManagedCaseLabelingQueue} onValidate={() => void validateManagedEvaluationCases()} onRun={() => void runEvaluation()} validating={validatingEvaluationCases} running={evaluating} />
      <div className="knowledge-evaluation-dataset-actions"><label>导入评测集<input type="file" accept=".json,.csv,application/json,text/csv" onChange={(event) => void importEvaluationDataset(event.target.files?.[0])} /></label><button onClick={() => exportEvaluationDataset('json')} disabled={!evaluationQuestions.trim()}>导出 JSON</button><button onClick={() => exportEvaluationDataset('csv')} disabled={!evaluationQuestions.trim()}>导出 CSV</button></div>
      {collectionId && <details className="knowledge-evaluation-gate"><summary>回归门禁阈值</summary><label>Hit@1 <input aria-label="门禁 Hit@1" type="number" min="0" max="1" step="0.01" value={evaluationGate.recall_at_1} onChange={(event) => setEvaluationGate({ ...evaluationGate, recall_at_1: Number(event.target.value) })} /></label><label>Hit@3 <input aria-label="门禁 Hit@3" type="number" min="0" max="1" step="0.01" value={evaluationGate.recall_at_3} onChange={(event) => setEvaluationGate({ ...evaluationGate, recall_at_3: Number(event.target.value) })} /></label><label>MRR <input aria-label="门禁 MRR" type="number" min="0" max="1" step="0.01" value={evaluationGate.mrr} onChange={(event) => setEvaluationGate({ ...evaluationGate, mrr: Number(event.target.value) })} /></label><button onClick={() => void saveEvaluationGate()} disabled={savingEvaluationGate}>{savingEvaluationGate ? '正在保存…' : '保存门禁阈值'}</button></details>}
      {evaluation?.quality_gate?.passed !== null && evaluation?.quality_gate?.passed !== undefined && <div className={`knowledge-evaluation-gate-status ${evaluation.quality_gate.passed ? 'passed' : 'failed'}`}><strong>{evaluation.quality_gate.passed ? '回归门禁通过' : '回归门禁未通过'}</strong>{evaluation.quality_gate.failures.map((item) => <span key={item.metric}>{item.metric} {Math.round(item.actual * 100)}% &lt; {Math.round(item.threshold * 100)}%</span>)}</div>}
      {graphAudit && <div className="knowledge-health knowledge-graph-audit"><span><b>{graphAudit.counts.low_confidence}</b> 低置信关系</span><span><b>{graphAudit.counts.missing_evidence}</b> 缺证据关系</span><span><b>{graphAudit.counts.similar_labels}</b> 相似实体组</span>{graphAudit.similar_labels.slice(0, 3).map((labels) => <small key={labels.join('-')}>{labels.join(' / ')}</small>)}</div>}
      {badCases.length > 0 && <div className="knowledge-bad-case-actions"><button onClick={() => void mergeBadCasesIntoEvaluation()}>合并 {badCases.length} 个 Bad Case</button><button onClick={() => void replayAllBadCases()} disabled={evaluating}>批量重放 {badCases.length} 个 Bad Case</button></div>}
      {evaluationComparison && <div className="knowledge-evaluation-comparison"><strong>较上次评测</strong><span>Hit@1 {evaluationComparison.recall_at_1 >= 0 ? '+' : ''}{Math.round(evaluationComparison.recall_at_1 * 100)}%</span><span>Hit@3 {evaluationComparison.recall_at_3 >= 0 ? '+' : ''}{Math.round(evaluationComparison.recall_at_3 * 100)}%</span><span>MRR {evaluationComparison.mrr >= 0 ? '+' : ''}{evaluationComparison.mrr.toFixed(3)}</span></div>}
      <details className="knowledge-duplicates"><summary>重复资料检测</summary><p>仅生成建议，不会自动删除任何资料。</p><button onClick={() => void checkDuplicates()} disabled={checkingDuplicates}>{checkingDuplicates ? '检测中…' : '检查重复资料'}</button>{duplicateSuggestions && <div>{duplicateSuggestions.filter((item) => !dismissedDuplicates.includes(`${item.left.id}-${item.right.id}`)).length ? duplicateSuggestions.filter((item) => !dismissedDuplicates.includes(`${item.left.id}-${item.right.id}`)).map((item) => <article key={`${item.left.id}-${item.right.id}`}><b>{Math.round(item.score * 100)}% · {item.reason}</b><button onClick={() => void openDetail(item.left.id)}>{item.left.title}</button><span>与</span><button onClick={() => void openDetail(item.right.id)}>{item.right.title}</button><button onClick={() => dismissDuplicate(`${item.left.id}-${item.right.id}`)}>忽略</button></article>) : <p>暂无待处理的高可信重复资料。</p>}</div>}</details>
      <details className="knowledge-evaluation-labeler"><summary>评测集切片标注</summary><p>输入真实问题，检索后勾选所有能够支持正确答案的切片。</p><div className="knowledge-evaluation-labeler-search"><input aria-label="待标注问题" value={evaluationLabelQuestion} onChange={(event) => setEvaluationLabelQuestion(event.target.value)} placeholder="输入一条真实用户问题" /><button onClick={() => void searchEvaluationCandidates()} disabled={searchingEvaluationCandidates || !evaluationLabelQuestion.trim()}>{searchingEvaluationCandidates ? '检索中…' : '检索候选切片'}</button></div>{evaluationLabelCandidates.length > 0 && <div className="knowledge-evaluation-candidates">{evaluationLabelCandidates.map((candidate) => <label key={candidate.chunk_id}><input type="checkbox" aria-label={`标记切片 ${candidate.chunk_id} 为相关`} checked={Boolean(candidate.chunk_id && selectedEvaluationChunkIds.includes(candidate.chunk_id))} onChange={(event) => { const id = candidate.chunk_id; if (!id) return; setSelectedEvaluationChunkIds((items) => event.target.checked ? [...items, id] : items.filter((item) => item !== id)); }} /><span><b>《{candidate.title}》</b> · {candidate.location || '未标注位置'} · {candidate.score.toFixed(3)}<small>{candidate.content}</small></span></label>)}</div>}<button onClick={addLabeledEvaluationCase} disabled={!selectedEvaluationChunkIds.length}>加入评测集</button></details>
      <details className="knowledge-evaluation"><summary>知识库质量评测{savedEvaluationCount ? ` · 已保存 ${savedEvaluationCount} 题` : ''}</summary><p>每行一个用例；可写“问题 || 预期资料标题”统计 Hit@1/3 与 MRR。通过 API 提供相关文档或切片 ID 时，还会计算标准 Recall、Precision 与 NDCG。</p><textarea value={evaluationQuestions} onChange={(event) => setEvaluationQuestions(event.target.value)} placeholder={'例如：\nReact 状态管理应该如何选择？ || React 状态管理\n缓存穿透有哪些解决方案？ || Redis 缓存'} rows={4} /><div className="knowledge-evaluation-actions"><button onClick={() => void runEvaluation()} disabled={evaluating || !evaluationQuestions.trim()}>{evaluating ? '评测中…' : '运行评测'}</button><button onClick={() => void saveEvaluationSuite()}>保存为回归问题</button></div>{evaluationHistory.length > 0 && <div className="knowledge-evaluation-history"><strong>最近评测趋势</strong>{evaluationHistory.map((item, index) => <div key={item.id}><span>{index === 0 ? '最新' : `第 ${index + 1} 次`} · {formatTime(item.created_at)} · H1 {Math.round((item.recall_at_1 || 0) * 100)}% · H3 {Math.round((item.recall_at_3 || 0) * 100)}% · MRR {item.mrr || 0} · 候选 {item.config.candidate_multiplier} · MMR {item.config.mmr_relevance_weight}</span><button onClick={() => void restoreEvaluationConfig(item)} disabled={applyingEvaluationRecommendation || evaluating}>{applyingEvaluationRecommendation ? '正在回退…' : '回退到此策略'}</button></div>)}</div>}{evaluation && <div className="knowledge-evaluation-results"><strong>{evaluation.judged_total ? <>Hit@1 {Math.round((evaluation.hit_at_1 ?? evaluation.recall_at_1 ?? 0) * 100)}% · Hit@3 {Math.round((evaluation.hit_at_3 ?? evaluation.recall_at_3 ?? 0) * 100)}% · MRR {evaluation.mrr || 0}</> : <>命中 {evaluation.hit_count} / {evaluation.total}</>}</strong>{evaluation.metrics?.k_values.map((k) => <p key={`metric-${k}`}>K={k} · Recall {Math.round((evaluation.metrics?.recall[String(k)] || 0) * 100)}% · Precision {Math.round((evaluation.metrics?.precision[String(k)] || 0) * 100)}% · NDCG {Math.round((evaluation.metrics?.ndcg[String(k)] || 0) * 100)}%</p>)}<p>召回通道覆盖：关键词 {evaluation.route_coverage.keyword || 0} · 向量 {evaluation.route_coverage.vector || 0} · 图谱 {evaluation.route_coverage.graph || 0} · 重排 {evaluation.route_coverage.reranker || 0}</p>{evaluation.recommendations?.map((item) => <div className="knowledge-evaluation-recommendation" key={item.field}>建议将{item.field === 'candidate_multiplier' ? '候选倍数' : 'MMR 相关性权重'}从 {item.current} 调整为 {item.suggested}：{item.reason}<button onClick={() => void applyEvaluationRecommendation(item)} disabled={!collectionId || applyingEvaluationRecommendation || evaluating}>{applyingEvaluationRecommendation ? '正在应用…' : '应用建议并重新评测'}</button></div>)}{evaluation.results.map((result) => <article key={result.question} className={result.status}><b>{result.status === 'pass' ? `通过${result.expected_rank ? ` · 第 ${result.expected_rank} 位` : ''}` : result.status === 'hit' ? '有召回' : '未命中'} · {result.question}</b>{result.hits[0] ? <p>《{result.hits[0].title}》 · 最终分数 {result.hits[0].score.toFixed(3)} · {result.hits[0].routes.join(' + ')}<br />{result.hits[0].excerpt}</p> : <p>建议补充对应资料，或调整问题措辞。</p>}{result.status !== 'pass' && <div className="knowledge-bad-case-action"><input aria-label={`失败原因：${result.question}`} value={badCaseReasons[result.question] || ''} onChange={(event) => setBadCaseReasons((items) => ({ ...items, [result.question]: event.target.value }))} placeholder="失败原因（可选）" maxLength={1000} /><button onClick={() => void saveEvaluationBadCase(result)} disabled={recordingBadCase === result.question}>{recordingBadCase === result.question ? '正在保存…' : '加入 Bad Case'}</button></div>}</article>)}</div>}{badCases.length > 0 && <div className="knowledge-bad-case-list"><strong>已记录的失败样例</strong>{badCases.slice(0, 10).map((item) => <div key={item.id || item.question}><span>{item.question}{item.reason ? ` · ${item.reason}` : ''}</span><button onClick={() => void replayBadCase(item)} disabled={!item.id || replayingBadCase === item.id}>{replayingBadCase === item.id ? '正在重放…' : '重放'}</button></div>)}</div>}</details>
      <div className="knowledge-evaluation-generator"><button onClick={() => void generateEvaluationSuite()} disabled={generatingEvaluation || !entries.some((entry) => entry.status === 'ready')}>{generatingEvaluation ? '正在生成评测用例…' : '自动生成评测用例'}</button><small>从当前知识库的已就绪资料生成问题与预期资料。</small></div>
      {evaluation?.answer_score !== null && evaluation?.answer_score !== undefined && <div className="knowledge-answer-quality"><b>答案质量 {Math.round(evaluation.answer_score * 100)}%</b><span>证据一致性 {Math.round((evaluation.grounded_rate || 0) * 100)}%</span><small>仅对带参考答案的自动生成用例运行本地模型判定。</small></div>}
      </div></details>
      <div className={`knowledge-workspace ${libraryCollapsed ? 'library-collapsed' : ''}`}>
      <aside className="knowledge-library">
        <button className="knowledge-library-toggle" onClick={() => setLibraryCollapsed((value) => !value)} aria-label={libraryCollapsed ? '展开主题菜单' : '收起主题菜单'}><span aria-hidden="true">‹</span></button>
        {!libraryCollapsed && <>
          <div className="knowledge-library-title">知识库 <span>{collections.length}</span></div>
          <nav className="knowledge-topics" aria-label="知识库">
            <button className={!collectionId ? 'active' : ''} onClick={() => selectCollection('')}>全部知识库</button>
            {collections.map((item) => {
              const isActive = collectionId === item.id;
              return <div className={`knowledge-collection-row ${isActive ? 'active' : ''}`} key={item.id}>
                <button className={isActive ? 'active' : ''} onClick={() => selectCollection(item.id)}>{item.name}</button>
                <button className="knowledge-collection-strategy" onClick={() => void openCollectionRetrievalConfig(item.id)} aria-label={`配置${item.name}检索策略`}>⚙</button>
                <button className="knowledge-collection-rename" onClick={() => { setRenameCollectionId(item.id); setRenameCollectionName(item.name); setCollectionActionError(''); }} aria-label={`重命名${item.name}`}><Pencil size={15} aria-hidden="true" /></button>
                <button className="knowledge-collection-delete" onClick={() => { setDeleteCollectionId(item.id); setCollectionActionError(''); }} aria-label={`删除${item.name}`}>×</button>
                {retrievalConfigCollectionId === item.id && <form className="knowledge-collection-confirm knowledge-collection-retrieval" onSubmit={(event) => { event.preventDefault(); void saveCollectionRetrievalConfig(); }}>
                  <strong>检索策略</strong><p>仅作用于“{item.name}”。</p>
                  {retrievalConfig ? <><label>Top-K<input aria-label="Top-K" value={retrievalConfig.top_k} onChange={(event) => setRetrievalConfig((current) => current ? { ...current, top_k: Number(event.target.value) } : current)} type="number" min="1" max="20" required /></label><label>候选倍数<input aria-label="候选倍数" value={retrievalConfig.candidate_multiplier} onChange={(event) => setRetrievalConfig((current) => current ? { ...current, candidate_multiplier: Number(event.target.value) } : current)} type="number" min="1" max="10" required /></label><label>最低相关度<input aria-label="最低相关度" value={retrievalConfig.minimum_relevance_score} onChange={(event) => setRetrievalConfig((current) => current ? { ...current, minimum_relevance_score: Number(event.target.value) } : current)} type="number" min="0" max="1" step="0.05" required /></label><label>MMR 相关性权重<input aria-label="MMR 相关性权重" value={retrievalConfig.mmr_relevance_weight} onChange={(event) => setRetrievalConfig((current) => current ? { ...current, mmr_relevance_weight: Number(event.target.value) } : current)} type="number" min="0" max="1" step="0.05" required /></label></> : <p>正在读取当前配置…</p>}
                  {collectionActionError && <small>{collectionActionError}</small>}<div><button type="submit" disabled={!retrievalConfig || retrievalConfigSaving}>{retrievalConfigSaving ? '保存中…' : '保存检索策略'}</button><button type="button" onClick={() => { setRetrievalConfigCollectionId(null); setCollectionActionError(''); }} disabled={retrievalConfigSaving}>取消</button></div>
                </form>}
                {renameCollectionId === item.id && <form className="knowledge-collection-confirm" onSubmit={(event) => { event.preventDefault(); void renameCollection(); }}>
                  <strong>重命名知识库</strong><input autoFocus value={renameCollectionName} onChange={(event) => setRenameCollectionName(event.target.value)} maxLength={80} />
                  {collectionActionError && <small>{collectionActionError}</small>}<div><button type="submit" disabled={!renameCollectionName.trim()}>保存</button><button type="button" onClick={() => { setRenameCollectionId(null); setCollectionActionError(''); }}>取消</button></div>
                </form>}
                {deleteCollectionId === item.id && <div className="knowledge-collection-confirm"><strong>确定删除此知识库？</strong><p>其中的资料、检索索引和图谱关系将一并永久删除。</p>{collectionActionError && <small>{collectionActionError}</small>}<div><button onClick={() => void removeCollection(item.id)}>确认删除</button><button onClick={() => { setDeleteCollectionId(null); setCollectionActionError(''); }}>取消</button></div></div>}
              </div>;
            })}
          </nav>
          {showCollectionForm ? <form className="knowledge-collection-form" onSubmit={(event) => { event.preventDefault(); void addCollection(); }}><input autoFocus value={collectionName} onChange={(event) => setCollectionName(event.target.value)} placeholder="例如：技术文档" maxLength={80} /><div><button type="submit" disabled={!collectionName.trim() || creatingCollection}>{creatingCollection ? '创建中' : '创建'}</button><button type="button" onClick={() => { setShowCollectionForm(false); setCollectionName(''); }}>取消</button></div></form> : <button className="knowledge-new-collection" onClick={() => setShowCollectionForm(true)}>＋ 新建知识库</button>}
          <div className="knowledge-library-title">主题 <span>{topics.length}</span></div><nav className="knowledge-topics" aria-label="知识主题"><button className={!topic ? 'active' : ''} onClick={() => setTopic('')}>全部资料</button>{topics.map((item) => <button key={item} className={topic === item ? 'active' : ''} onClick={() => setTopic(item)}>{item}</button>)}</nav>
        </>}
      </aside>
      <main className={`knowledge-main ${selected && !detailPanelClosed ? 'has-detail' : 'no-detail'}`}>
      <div className="knowledge-main-content">
      <div className="knowledge-main-toolbar">
      <div className="knowledge-ask">
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="搜索资料、主题或关系…" />
        <button onClick={() => void ask()} disabled={!question.trim() || searching}>{searching ? '检索中' : '检索'}</button>
        <label className="knowledge-upload-button">{uploading ? '正在导入…' : '导入资料'}<input type="file" accept=".pdf,.docx,.xlsx,.xls,.pptx,.html,.mhtml,.md,.txt,.png,.jpg,.jpeg,.webp" onChange={(event) => void upload(event.target.files?.[0])} disabled={uploading || !collectionId} /></label>
      </div>
      <div className="knowledge-view-controls"><div className="knowledge-view-tabs" role="tablist" aria-label="知识可视化方式"><button className={knowledgeView === 'mindmap' ? 'active' : ''} aria-pressed={knowledgeView === 'mindmap'} onClick={() => setKnowledgeView('mindmap')}>文档思维导图</button><button className={knowledgeView === 'relations' ? 'active' : ''} aria-pressed={knowledgeView === 'relations'} onClick={() => setKnowledgeView('relations')}>跨资料关系图</button></div>{selected && detailPanelClosed && <button className="knowledge-detail-toggle" onClick={() => setDetailPanelClosed(false)}>打开资料详情</button>}</div>
      </div>
      <div className="knowledge-main-scroll">
      {knowledgeView === 'mindmap' ? <section className="knowledge-mindmap-panel" aria-label="当前文档思维导图">
        <div className="knowledge-graph-heading"><div><span>DOCUMENT MAP</span><h2>{selected?.title || '选择一份资料'}</h2></div><small>{mindMap?.nodes.length || 0} 个摘要节点</small></div>
        {selected && mindMap ? <DocumentMindMap nodes={mindMap.nodes} onOpenEvidence={setMindMapEvidence} /> : <p className="knowledge-empty">选择下方一份已就绪资料，查看全文思维导图。</p>}
        {mindMapEvidence.length > 0 && <div className="mindmap-source-panel"><strong>原文证据</strong>{selected?.chunks?.filter((chunk) => mindMapEvidence.includes(chunk.id)).map((chunk) => <article key={chunk.id}>{chunk.location && <small>{chunk.location}</small>}<p>{chunk.content}</p></article>)}</div>}
      </section> : <>
      {graphNode && !graphEdge && <div className="knowledge-edge-evidence"><strong>{activeGraphNode?.label} · 实体校正</strong>{collectionId ? <>{editingGraphEntity ? <span className="knowledge-graph-edit"><input value={graphEntityDraft} onChange={(event) => setGraphEntityDraft(event.target.value)} maxLength={120} /><button onClick={() => void saveGraphEntity()} disabled={savingGraphRelation}>保存</button><button onClick={() => setEditingGraphEntity(false)} disabled={savingGraphRelation}>取消</button></span> : <span className="knowledge-graph-edit"><button onClick={() => { setGraphEntityDraft(activeGraphNode?.label || ''); setEditingGraphEntity(true); }}>重命名实体</button><button onClick={() => setConfirmingEntityDelete(true)}>删除实体</button></span>}{confirmingEntityDelete && <p className="knowledge-graph-confirm">删除会移除当前知识库中与该实体相连的全部关系。<button onClick={() => void removeGraphEntity()} disabled={savingGraphRelation}>确认删除</button><button onClick={() => setConfirmingEntityDelete(false)} disabled={savingGraphRelation}>取消</button></p>}</> : <p>请选择一个具体知识库后再编辑实体。</p>}</div>}
      {graph.nodes.length > 0 && <><div className="knowledge-graph-filters"><label>节点<select value={graphKindFilter} onChange={(event) => setGraphKindFilter(event.target.value as 'all' | 'topic' | 'entity')}><option value="all">全部</option><option value="topic">主题</option><option value="entity">实体</option></select></label><label>最低置信度<select value={graphConfidence} onChange={(event) => setGraphConfidence(Number(event.target.value))}><option value={0}>全部</option><option value={0.5}>50%+</option><option value={0.75}>75%+</option></select></label><small>{filteredGraphNodes.length} 节点 · {filteredGraphEdges.length} 关系</small></div><div className="knowledge-graph-search"><input value={graphQuery} onChange={(event) => setGraphQuery(event.target.value)} placeholder="搜索图谱节点…" /><button onClick={() => { const matched = filteredGraphNodes.find((node) => node.label.toLowerCase().includes(graphQuery.trim().toLowerCase())); if (matched) { setGraphNode(matched.id); setGraphEdge(null); setGraphSummary(null); } }} disabled={!graphQuery.trim()}>定位</button>{graphNode && <button onClick={() => { setGraphNode(null); setGraphQuery(''); setGraphSummary(null); }}>清除聚焦</button>}</div><KnowledgeGraphCanvas nodes={filteredGraphNodes} edges={filteredGraphEdges} onSelect={(id) => { setGraphNode(id); setGraphEdge(null); setGraphSummary(null); }} onSelectEdge={(edge) => { setGraphEdge(edge); setGraphSummary(null); setEditingGraphRelation(false); }} activeNodeId={graphNode} storageKey={collectionId || 'all'} />{(graphNode || graphEdge) && <div className="knowledge-edge-evidence"><strong>{graphEdge ? `${graphLabel(graphEdge.source)} —${graphEdge.relation}→ ${graphLabel(graphEdge.target)}` : `${activeGraphNode?.label} · 实体`}</strong>{graphEdge && <small>抽取置信度 {Math.round((graphEdge.confidence ?? 0) * 100)}%</small>}{graphEdge?.evidence && <p>{graphEdge.evidence}</p>}<button onClick={() => void summarizeSelectedGraph()} disabled={summarizingGraph}>{summarizingGraph ? '正在生成摘要…' : '生成基于证据的摘要'}</button>{graphEdge && <>{editingGraphRelation ? <span className="knowledge-graph-edit"><select value={graphRelationDraft} onChange={(event) => setGraphRelationDraft(event.target.value)}><option>使用</option><option>基于</option><option>依赖</option><option>包含</option><option>实现</option><option>用于</option><option>导致</option><option>优化</option><option>关联</option><option>涉及</option></select><button onClick={() => void saveGraphRelation()} disabled={savingGraphRelation}>保存</button><button onClick={() => setEditingGraphRelation(false)} disabled={savingGraphRelation}>取消</button></span> : <span className="knowledge-graph-edit"><button onClick={() => { setGraphRelationDraft(graphEdge.relation); setEditingGraphRelation(true); }}>修改关系</button><button onClick={() => void removeGraphRelation()} disabled={savingGraphRelation}>删除关系</button></span>}</>}{graphSummary && <div className="knowledge-graph-summary"><b>摘要</b><p>{graphSummary.summary}</p><small>{graphSummary.evidence_count} 条来源事实支撑</small></div>}{graphEdge?.document_id && <button onClick={() => void openDetail(graphEdge.document_id!)}>打开来源资料</button>}</div>}</>}
      <section className="knowledge-graph" aria-label="知识图谱"><div className="knowledge-graph-heading"><div><span>RELATION MAP</span><h2>{topic || '全部知识图谱'}</h2></div><small>{graph.nodes.length} 个节点 · {graph.edges.length} 条关系</small></div>{graph.nodes.length === 0 ? <p className="knowledge-empty">导入资料后自动生成图谱。</p> : <div className="knowledge-graph-canvas"><svg ref={graphRef} viewBox="0 0 520 410" role="img" aria-label="可拖动知识实体关系网络" onWheel={(event) => { event.preventDefault(); setGraphZoom((value) => Math.max(.55, Math.min(2.2, value + (event.deltaY < 0 ? .12 : -.12)))); }} onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); setDragging({ id: null, ...graphPointer(event) }); }} onPointerMove={graphMove} onPointerUp={() => setDragging(null)}><g transform={`translate(${graphPan.x} ${graphPan.y}) scale(${graphZoom})`}>{graph.edges.map((edge, index) => { const source = graphPosition.get(edge.source); const target = graphPosition.get(edge.target); const sourceOffset = nodeOffsets[edge.source] || { x: 0, y: 0 }; const targetOffset = nodeOffsets[edge.target] || { x: 0, y: 0 }; const selected = graphEdge?.source === edge.source && graphEdge?.target === edge.target && graphEdge?.relation === edge.relation; return source && target ? <line className={selected ? 'selected' : ''} key={`${edge.source}-${edge.target}-${index}`} x1={source.x + sourceOffset.x} y1={source.y + sourceOffset.y} x2={target.x + targetOffset.x} y2={target.y + targetOffset.y} onPointerDown={(event) => { event.stopPropagation(); setGraphEdge(edge); }} /> : null; })}{graphNodes.map((node) => { const point = graphPosition.get(node.id)!; const offset = nodeOffsets[node.id] || { x: 0, y: 0 }; const selected = graphNode === node.id; return <g key={node.id} className={`knowledge-graph-svg-node ${node.kind} ${selected ? 'selected' : ''}`} transform={`translate(${point.x + offset.x} ${point.y + offset.y})`} onPointerDown={(event) => { event.stopPropagation(); setGraphNode(node.id); setGraphEdge(null); setDragging({ id: node.id, ...graphPointer(event) }); }}><circle r={node.kind === 'topic' ? 28 : 17 + Math.min(node.document_count, 5)} /><text y={node.kind === 'topic' ? 45 : 34}>{node.label.slice(0, 12)}</text></g>; })}</g></svg><div className="knowledge-graph-tools"><button onClick={() => { setGraphPan({ x: 0, y: 0 }); setGraphZoom(1); setNodeOffsets({}); }}>重置视图</button><span>{Math.round(graphZoom * 100)}%</span></div><div className="knowledge-graph-legend"><span><i className="topic" />主题</span><span><i />实体</span>{activeGraphNode && <strong>{activeGraphNode.label} · {activeGraphNode.document_count} 篇资料</strong>}</div>{graphEdge && <div className="knowledge-edge-evidence"><strong>{graphLabel(graphEdge.source)} —{graphEdge.relation}→ {graphLabel(graphEdge.target)}</strong><small>抽取置信度 {Math.round((graphEdge.confidence ?? 0) * 100)}%</small><p>{graphEdge.evidence || '该关系暂无可展示的原文证据。'}</p><button onClick={() => graphEdge.document_id && void openDetail(graphEdge.document_id)}>打开来源资料</button></div>}</div>}</section>
      </>}
      <details className="knowledge-add"><summary>手动添加资料</summary><div className="knowledge-add-form">
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="标题" maxLength={200} />
        <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="主题（可选）" maxLength={50} />
        <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="来源链接（可选）" maxLength={2000} />
        <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="正文内容" rows={5} />
        <button onClick={() => void add()} disabled={!title.trim() || !content.trim() || !collectionId}>保存资料</button>
      </div></details>

      {hits !== null && (
        <div className="knowledge-hits">
          <h2>检索结果</h2>
          {hits.length === 0 ? (
            <p className="knowledge-empty">没有找到相关内容</p>
          ) : (
            <ul className="knowledge-hit-list">
              {hits.map((hit) => (
                <li key={hit.chunk_id || hit.document_id || hit.entry_id} className="knowledge-hit-item">
                  <div className="knowledge-hit-title">{hit.title}</div>
                  {hit.location && <small>{hit.location}</small>}
                  <p className="knowledge-hit-content">{hit.content}</p>
                  <div className="knowledge-hit-meta">{[...(hit.routes || []).map((route) => ({ keyword: '关键词', vector: '向量', graph: '图谱', reranker: '重排' }[route] || route)), `${Math.round(Math.max(0, Math.min(1, hit.score)) * 100)}%`].join(' · ')}</div>
                  {(hit.document_id || hit.entry_id) && <button onClick={() => void openDetail(hit.document_id || hit.entry_id!, hit.chunk_id || null)}>打开资料：{hit.title}</button>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {loading ? (
        <p className="knowledge-empty">正在加载知识库…</p>
      ) : entries.length === 0 ? (
        <p className="knowledge-empty">知识库还是空的，导入资料或手动添加内容。</p>
      ) : (
        <><div className="knowledge-bulk-bar"><label><input type="checkbox" checked={entries.length > 0 && selectedEntryIds.length === entries.length} onChange={() => setSelectedEntryIds(selectedEntryIds.length === entries.length ? [] : entries.map((entry) => entry.id))} /> 已选 {selectedEntryIds.length} 项</label><select value={bulkDestinationId} onChange={(event) => setBulkDestinationId(event.target.value)}><option value="">移动到知识库…</option>{collections.filter((item) => item.id !== collectionId).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button onClick={() => void runBulk('move')} disabled={bulkWorking || !selectedEntryIds.length || !bulkDestinationId}>移动</button><button onClick={() => void runBulk('reindex')} disabled={bulkWorking || !selectedEntryIds.length}>重新索引</button><button className="danger" onClick={() => void runBulk('delete')} disabled={bulkWorking || !selectedEntryIds.length}>删除</button></div>
        <ul className="knowledge-list">
          {entries.map((entry) => (
            <li key={entry.id} className="knowledge-item">
              <label className="knowledge-item-select"><input type="checkbox" checked={selectedEntryIds.includes(entry.id)} onChange={() => toggleEntry(entry.id)} aria-label={`选择${entry.title}`} /></label>
              <button className="knowledge-item-main" onClick={() => void openDetail(entry.id)}>
                <span className="knowledge-item-title">{entry.title}</span>
                <span className="knowledge-item-meta">{entry.status === 'queued' || entry.status === 'indexing' ? indexProgress[entry.id]?.message || (entry.status === 'queued' ? '排队等待索引' : '正在解析、生成图谱与向量…') : entry.status === 'failed' ? `导入失败：${indexProgress[entry.id]?.message || entry.error_message || '请重试'}` : `${entry.category || '文档'} · ${entry.source_type === 'upload' ? '本地文件' : entry.source_type === 'scrape' ? '抓取' : '手动'}`}</span>
              </button>
              <span className="knowledge-item-time">{formatTime(entry.updated_at)}</span>
              <button className="knowledge-delete" onClick={() => void remove(entry.id)}>删除</button>
            </li>
          ))}
        </ul></>
      )}

      </div>
      </div>
      {selected && !detailPanelClosed && <aside className="knowledge-detail-panel is-open" aria-label="资料详情">
        <div className="knowledge-detail">
          <div className="knowledge-detail-header">
            <h2>{editingDocument ? '编辑资料' : selected.title}</h2>
            <div>{selected.source_type !== 'upload' && !editingDocument && <button onClick={beginEdit}>编辑</button>}<button className="knowledge-detail-delete" onClick={() => void remove(selected.id)}>删除资料</button><button onClick={() => { setDetailPanelClosed(true); setEditingDocument(false); }}>关闭</button></div>
          </div>
          {selected.index_stats && <div className="knowledge-index-stats"><span>{selected.index_stats.chunk_count} 切片</span><span>{selected.index_stats.embedding_count} 向量</span><span>{selected.index_stats.graph_node_count} 节点</span><span>{selected.index_stats.graph_edge_count} 关系</span></div>}
          <div className="knowledge-maintenance"><button onClick={() => void reindex(false)} disabled={maintaining}>{maintaining ? '已加入后台队列…' : '重新索引图谱与向量'}</button><button onClick={() => void reindex(true)} disabled={maintaining}>仅补建向量</button></div>
          {selected.source_url && (
            <a href={selected.source_url} target="_blank" rel="noreferrer">查看原文</a>
          )}
          {selected.source_type === 'upload' && <section className="knowledge-original-source"><div><strong>原文件</strong><a href={originalSourceUrl} target="_blank" rel="noreferrer">在新标签页打开</a></div>{isPreviewableSource(selected) && <iframe src={originalSourceUrl} title={`原文件预览：${selected.title}`} />}</section>}
          {editingDocument ? <div className="knowledge-edit-form"><input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} maxLength={200} /><textarea value={editContent} onChange={(event) => setEditContent(event.target.value)} rows={13} maxLength={50000} /><div><button onClick={() => void saveEdit()} disabled={!editTitle.trim() || !editContent.trim()}>保存并重新索引</button><button onClick={() => setEditingDocument(false)}>取消</button></div></div> : selected.chunks?.length ? <div className="knowledge-source-chunks">{selected.chunks.map((chunk, index) => <KnowledgeChunkEditor key={chunk.id} documentId={selected.id} chunk={chunk} index={index} active={chunk.id === citationChunkId} onUpdated={updateSelectedChunk} elementRef={(element) => { sourceChunkRefs.current[chunk.id] = element; }} />)}</div> : <pre className="knowledge-detail-content">{selected.content}</pre>}
        </div>
      </aside>}
      </main></div>
    </section>
  );
}
