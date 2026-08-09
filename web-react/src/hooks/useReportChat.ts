import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  applyReportSuggestion,
  chatAboutReport,
  deleteReportAttachment,
  uploadReportAttachments,
} from '../api/reports';
import type { DailyReport, ReportAttachment, ReportChatMessage, ReportSuggestion } from '../types';

type Props = { report: DailyReport | null; onReportUpdated: (report: DailyReport) => void; onError: (message: string) => void };

export function useReportChat({ report, onReportUpdated, onError }: Props) {
  const [attachments, setAttachments] = useState<ReportAttachment[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [suggestion, setSuggestion] = useState<ReportSuggestion | null>(null);
  const [messages, setMessages] = useState<ReportChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const messageNumber = useRef(0);
  const reportRef = useRef(report);
  reportRef.current = report;
  const availableAttachments = useMemo(() => report?.attachments ?? attachments, [report, attachments]);

  useEffect(() => {
    setAttachments([]);
    setSelectedIds([]);
    setSuggestion(null);
    setMessages([]);
  }, [report?.date, report?.revision]);

  const upload = useCallback(async (files: File[], preserve: boolean) => {
    if (!report || files.length === 0) return;
    setBusy(true);
    try {
      const saved = await uploadReportAttachments(report.date, files, preserve);
      setAttachments(saved.report.attachments ?? saved.attachments);
      onReportUpdated(saved.report);
    } catch (error) { onError(error instanceof Error ? error.message : '附件上传失败'); } finally { setBusy(false); }
  }, [onError, onReportUpdated, report]);

  const remove = useCallback(async (attachmentId: string) => {
    if (!report) return;
    setBusy(true);
    try {
      const updated = await deleteReportAttachment(report.date, attachmentId);
      setAttachments(updated.attachments ?? []);
      setSelectedIds((current) => current.filter((id) => id !== attachmentId));
      onReportUpdated(updated);
    } catch (error) { onError(error instanceof Error ? error.message : '附件删除失败'); } finally { setBusy(false); }
  }, [onError, onReportUpdated, report]);

  const toggleAttachment = useCallback((attachmentId: string) => {
    setSelectedIds((current) => current.includes(attachmentId) ? current.filter((id) => id !== attachmentId) : [...current, attachmentId]);
  }, []);

  const send = useCallback(async (message: string) => {
    if (!report || !message.trim()) return;
    const content = message.trim();
    const reportDate = report.date;
    const expectedRevision = report.revision;
    setBusy(true);
    setMessages((current) => [...current, { id: `user-${++messageNumber.current}`, role: 'user', content }]);
    try {
      const result = await chatAboutReport(reportDate, content, selectedIds, expectedRevision);
      if (
        reportRef.current?.date !== reportDate
        || reportRef.current?.revision !== expectedRevision
      ) return;
      setSuggestion(result.suggestion);
      setMessages((current) => [...current, {
        id: `assistant-${++messageNumber.current}`,
        role: 'assistant',
        content: result.reply || result.suggestion.reply,
      }]);
    }
    catch (error) { onError(error instanceof Error ? error.message : '日报对话失败'); }
    finally { setBusy(false); }
  }, [onError, report, selectedIds]);

  const apply = useCallback(async () => {
    if (!report || !suggestion) return;
    setBusy(true);
    try { onReportUpdated(await applyReportSuggestion(report.date, suggestion.id, report.revision)); setSuggestion(null); }
    catch (error) { onError(error instanceof Error ? error.message : '应用建议失败'); }
    finally { setBusy(false); }
  }, [onError, onReportUpdated, report, suggestion]);

  return { attachments: availableAttachments, selectedIds, suggestion, messages, busy, upload, remove, toggleAttachment, send, apply };
}
