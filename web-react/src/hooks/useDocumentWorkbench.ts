import { useCallback, useEffect, useRef, useState } from 'react';

import {
  DocumentApiError,
  deleteDocument,
  generateDocumentDraft,
  getDocumentDraft,
  listDocumentDrafts,
  listDocuments,
  saveDocumentDraft,
  uploadDocument,
} from '../api/documents';
import type { DocumentDraft, DocumentTemplate, WorkbenchDocument } from '../types';

export type DocumentPane = 'library' | 'compose' | 'editor';
export type DocumentSaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : '操作失败，请稍后重试';

export function useDocumentWorkbench() {
  const [documents, setDocuments] = useState<WorkbenchDocument[]>([]);
  const [drafts, setDrafts] = useState<DocumentDraft[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [draft, setDraft] = useState<DocumentDraft | null>(null);
  const [template, setTemplate] = useState<DocumentTemplate>('prd');
  const [instructions, setInstructions] = useState('');
  const [title, setTitle] = useState('');
  const [markdown, setMarkdownState] = useState('');
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveState, setSaveState] = useState<DocumentSaveState>('idle');
  const [error, setError] = useState('');
  const [mobilePane, setMobilePane] = useState<DocumentPane>('library');
  const draftRef = useRef<DocumentDraft | null>(null);

  const applyDraft = useCallback((next: DocumentDraft) => {
    draftRef.current = next;
    setDraft(next);
    setTitle(next.title);
    setMarkdownState(next.markdown);
    setSaveState('saved');
    setDrafts((current) => [next, ...current.filter((item) => item.id !== next.id)]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listDocuments(), listDocumentDrafts()])
      .then(([nextDocuments, nextDrafts]) => {
        if (cancelled) return;
        setDocuments(nextDocuments);
        setDrafts(nextDrafts);
        if (nextDrafts[0]) applyDraft(nextDrafts[0]);
        setReady(true);
      })
      .catch((caught) => { if (!cancelled) setError(errorMessage(caught)); });
    return () => { cancelled = true; };
  }, [applyDraft]);

  const toggleDocument = useCallback((id: string) => {
    if (documents.find((item) => item.id === id)?.extraction_status !== 'ready') return;
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }, [documents]);

  const upload = useCallback(async (files: File[]) => {
    if (!files.length || busy) return;
    setBusy(true); setError('');
    try {
      const uploaded = await Promise.all(files.map(uploadDocument));
      setDocuments((current) => [...uploaded, ...current]);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }, [busy]);

  const remove = useCallback(async (id: string) => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await deleteDocument(id);
      setDocuments((current) => current.filter((item) => item.id !== id));
      setSelectedIds((current) => current.filter((item) => item !== id));
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }, [busy]);

  const generate = useCallback(async () => {
    if (!selectedIds.length || busy) return;
    setBusy(true); setError('');
    try {
      const generated = await generateDocumentDraft(template, selectedIds, instructions);
      applyDraft(generated);
      setMobilePane('editor');
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }, [applyDraft, busy, instructions, selectedIds, template]);

  const openDraft = useCallback(async (id: string) => {
    if (busy) return;
    setBusy(true); setError('');
    try { applyDraft(await getDocumentDraft(id)); setMobilePane('editor'); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }, [applyDraft, busy]);

  const setMarkdown = useCallback((value: string) => { setMarkdownState(value); setSaveState('dirty'); }, []);
  const setDraftTitle = useCallback((value: string) => { setTitle(value); setSaveState('dirty'); }, []);

  const save = useCallback(async () => {
    const current = draftRef.current;
    if (!current || busy || !title.trim() || !markdown.trim()) return;
    setBusy(true); setError(''); setSaveState('saving');
    try { applyDraft(await saveDocumentDraft(current.id, title.trim(), markdown.trim(), current.revision)); }
    catch (caught) {
      setSaveState(caught instanceof DocumentApiError && caught.status === 409 ? 'conflict' : 'error');
      setError(errorMessage(caught));
    } finally { setBusy(false); }
  }, [applyDraft, busy, markdown, title]);

  const reloadDraft = useCallback(async () => {
    const current = draftRef.current;
    if (!current || busy) return;
    setBusy(true); setError('');
    try { applyDraft(await getDocumentDraft(current.id)); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }, [applyDraft, busy]);

  return {
    documents, drafts, selectedIds, draft, template, instructions, title, markdown, ready, busy, saveState, error, mobilePane,
    setTemplate, setInstructions, setMobilePane, toggleDocument, upload, remove, generate, openDraft, setTitle: setDraftTitle,
    setMarkdown, save, reloadDraft,
  };
}
