import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  MAX_DRAWIO_XML_CHARS,
  hasSavedDrawioDiagram,
  readStoredDrawioDiagram,
  writeStoredDrawioDiagram,
  type DrawioDiagramSource,
} from './drawioStorage';

const DEFAULT_EMBED_URL = 'https://embed.diagrams.net/?embed=1&proto=json&spin=1&libraries=1';
const AUTOSAVE_DELAY_MS = 400;
const MAX_MESSAGE_CHARS = MAX_DRAWIO_XML_CHARS + 64 * 1024;
const MAX_MERMAID_CHARS = 512 * 1024;
type ExportFormat = 'png' | 'svg' | 'xml';

type IncomingDrawioMessage = Record<string, unknown> & {
  event: 'init' | 'autosave' | 'save' | 'export' | 'status';
};

type PendingImport = { request: number; code: string };
type PendingSave = { xml: string; acknowledgeSave: boolean; source: DrawioDiagramSource };

export interface DrawioEditorProps {
  mermaidCode: string;
  /** Increment this only after the user explicitly asks to import the current Mermaid source. */
  importRequest?: number;
  /** The parent clears an import command as soon as this editor has accepted it. */
  onImportConsumed?: (request: number) => void;
  /** Reports meaningful canvas content immediately, including during local autosave debounce. */
  onDiagramPresenceChange?: (hasContent: boolean) => void;
  onSavedDiagramChange?: (hasSavedDiagram: boolean) => void;
}

function getEmbedUrl(): URL {
  const configured = import.meta.env.VITE_DRAWIO_EMBED_URL?.trim();
  if (configured) {
    try {
      const candidate = new URL(configured);
      // Build-time configuration is trusted, but never permit an insecure or opaque origin.
      if (candidate.protocol === 'https:' && candidate.origin !== 'null') return candidate;
    } catch {
      // Fall through to the known-safe default.
    }
  }
  return new URL(DEFAULT_EMBED_URL);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseIncomingMessage(data: unknown): IncomingDrawioMessage | null {
  if (typeof data !== 'string' || data.length > MAX_MESSAGE_CHARS) return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (!isRecord(parsed)) return null;
    const event = parsed.event;
    if (event !== 'init' && event !== 'autosave' && event !== 'save' && event !== 'export' && event !== 'status') return null;
    return parsed as IncomingDrawioMessage;
  } catch {
    return null;
  }
}

function getXml(message: IncomingDrawioMessage): string | null {
  return typeof message.xml === 'string' && message.xml.length <= MAX_DRAWIO_XML_CHARS ? message.xml : null;
}

function filenameFor(format: ExportFormat): string {
  if (format === 'png') return 'iris-diagram.png';
  if (format === 'svg') return 'iris-diagram.svg';
  return 'iris-diagram.drawio';
}

function acceptsMime(format: ExportFormat, mime: string): boolean {
  if (format === 'png') return mime === 'image/png';
  if (format === 'svg') return mime === 'image/svg+xml';
  return mime === 'application/xml' || mime === 'application/xml+drawio' || mime === 'text/xml' || mime === 'application/vnd.jgraph.mxfile';
}

function dataUriToBlob(data: string, format: ExportFormat): Blob | null {
  if (data.length > MAX_MESSAGE_CHARS) return null;
  const match = /^data:([^;,]+)(;base64)?,([\s\S]*)$/i.exec(data);
  if (!match || !acceptsMime(format, match[1].toLowerCase())) return null;
  try {
    if (match[2]) {
      const binary = atob(match[3]);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      return new Blob([bytes], { type: match[1] });
    }
    return new Blob([decodeURIComponent(match[3])], { type: match[1] });
  } catch {
    return null;
  }
}

function rawXmlToBlob(data: string): Blob | null {
  if (data.length > MAX_DRAWIO_XML_CHARS || !data.trim().startsWith('<')) return null;
  const parsed = new DOMParser().parseFromString(data, 'application/xml');
  if (parsed.querySelector('parsererror')) return null;
  const root = parsed.documentElement?.localName;
  if (root !== 'mxfile' && root !== 'mxGraphModel') return null;
  return new Blob([data], { type: 'application/xml;charset=utf-8' });
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function DrawioEditor({
  mermaidCode,
  importRequest = 0,
  onImportConsumed,
  onDiagramPresenceChange,
  onSavedDiagramChange,
}: DrawioEditorProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const persistTimerRef = useRef<number | null>(null);
  const pendingSaveRef = useRef<PendingSave | null>(null);
  const readyRef = useRef(false);
  const pendingImportRef = useRef<PendingImport | null>(null);
  const handledImportRef = useRef(0);
  const pendingExportRef = useRef<ExportFormat | null>(null);
  const pendingSourceRef = useRef<DrawioDiagramSource>('drawio');
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [status, setStatus] = useState('等待专业画布就绪');
  const embedUrl = useMemo(getEmbedUrl, []);
  const targetOrigin = embedUrl.origin;

  const postToFrame = useCallback(
    (payload: Record<string, unknown>): boolean => {
      const target = iframeRef.current?.contentWindow;
      if (!target) return false;
      target.postMessage(JSON.stringify(payload), targetOrigin);
      return true;
    },
    [targetOrigin]
  );

  const sendSavedDiagram = useCallback(() => {
    const saved = readStoredDrawioDiagram();
    postToFrame({
      action: 'load',
      xml: saved?.xml ?? '',
      autosave: 1,
      fit: 1,
      title: 'Iris 流程图',
      noExitBtn: 1,
      exportProtocol: true,
    });
    onSavedDiagramChange?.(Boolean(saved?.xml.trim()));
  }, [onSavedDiagramChange, postToFrame]);

  const sendMermaidDiagram = useCallback(
    (code: string) => {
      if (!code.trim() || code.length > MAX_MERMAID_CHARS) {
        setStatus('Mermaid 源码为空或过大，无法导入');
        return false;
      }
      pendingSourceRef.current = 'mermaid';
      const sent = postToFrame({
        action: 'load',
        descriptor: { format: 'mermaid', data: code, wrap: true },
        sourceMetadata: { key: 'mermaidSource', value: code },
        autosave: 1,
        fit: 1,
      });
      if (sent) setStatus('已导入 Mermaid，正在打开专业画布');
      return sent;
    },
    [postToFrame]
  );

  const sendPendingImport = useCallback(() => {
    const pending = pendingImportRef.current;
    pendingImportRef.current = null;
    if (pending) sendMermaidDiagram(pending.code);
  }, [sendMermaidDiagram]);

  const writePendingSave = useCallback(
    (pending: PendingSave, updateStatus: boolean) => {
      const saved = writeStoredDrawioDiagram({
        version: 1,
        xml: pending.xml,
        updatedAt: Date.now(),
        source: pending.source,
      });
      if (!saved) {
        if (updateStatus) setStatus('无法保存到本地浏览器存储');
        return false;
      }
      onSavedDiagramChange?.(true);
      if (updateStatus) setStatus('已自动保存到本地');
      if (pending.acknowledgeSave) postToFrame({ action: 'status', modified: false });
      return true;
    },
    [onSavedDiagramChange, postToFrame]
  );

  const persistXml = useCallback(
    (xml: string, acknowledgeSave: boolean) => {
      if (persistTimerRef.current !== null) window.clearTimeout(persistTimerRef.current);
      pendingSaveRef.current = { xml, acknowledgeSave, source: pendingSourceRef.current };
      pendingSourceRef.current = 'drawio';
      onDiagramPresenceChange?.(Boolean(xml.trim()));
      persistTimerRef.current = window.setTimeout(() => {
        const pending = pendingSaveRef.current;
        pendingSaveRef.current = null;
        persistTimerRef.current = null;
        if (pending) writePendingSave(pending, true);
      }, AUTOSAVE_DELAY_MS);
    },
    [onDiagramPresenceChange, writePendingSave]
  );

  const handleExport = useCallback(
    (message: IncomingDrawioMessage) => {
      const format = pendingExportRef.current;
      if (!format || typeof message.data !== 'string') return;
      const blob = message.data.startsWith('data:') ? dataUriToBlob(message.data, format) : format === 'xml' ? rawXmlToBlob(message.data) : null;
      if (!blob) {
        pendingExportRef.current = null;
        setExporting(null);
        setStatus('专业画布返回的导出数据无效');
        return;
      }
      pendingExportRef.current = null;
      setExporting(null);
      downloadBlob(blob, filenameFor(format));
      setStatus(`已导出 ${format.toUpperCase()} 文件`);
    },
    []
  );

  useEffect(() => {
    const hasContent = hasSavedDrawioDiagram();
    onSavedDiagramChange?.(hasContent);
    onDiagramPresenceChange?.(hasContent);
  }, [onDiagramPresenceChange, onSavedDiagramChange]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const iframeWindow = iframeRef.current?.contentWindow;
      if (!iframeWindow || event.origin !== targetOrigin || event.source !== iframeWindow) return;
      const message = parseIncomingMessage(event.data);
      if (!message) return;

      if (message.event === 'init') {
        readyRef.current = true;
        const pendingImport = pendingImportRef.current;
        if (pendingImport) sendPendingImport();
        else sendSavedDiagram();
        setStatus('专业画布已就绪');
        return;
      }

      if (message.event === 'autosave' || message.event === 'save') {
        const xml = getXml(message);
        if (xml !== null) persistXml(xml, message.event === 'save');
        return;
      }

      if (message.event === 'export') handleExport(message);
    };

    window.addEventListener('message', onMessage);
    return () => {
      window.removeEventListener('message', onMessage);
      if (persistTimerRef.current !== null) window.clearTimeout(persistTimerRef.current);
      const pendingSave = pendingSaveRef.current;
      pendingSaveRef.current = null;
      if (pendingSave) writePendingSave({ ...pendingSave, acknowledgeSave: false }, false);
    };
  }, [handleExport, persistXml, sendPendingImport, sendSavedDiagram, targetOrigin, writePendingSave]);

  useEffect(() => {
    if (!importRequest || importRequest === handledImportRef.current) return;
    handledImportRef.current = importRequest;
    pendingImportRef.current = { request: importRequest, code: mermaidCode };
    onImportConsumed?.(importRequest);
    if (readyRef.current) sendPendingImport();
  }, [importRequest, mermaidCode, onImportConsumed, sendPendingImport]);

  const requestExport = (format: ExportFormat) => {
    if (pendingExportRef.current) return;
    pendingExportRef.current = format;
    setExporting(format);
    if (!postToFrame({ action: 'export', format, spin: '1', border: 0, scale: 1 })) {
      pendingExportRef.current = null;
      setExporting(null);
      setStatus('专业画布尚未就绪，暂时不能导出');
      return;
    }
    setStatus(`正在准备 ${format.toUpperCase()} 导出`);
  };

  return (
    <section className="drawio-editor" aria-label="Draw.io 专业流程图画布">
      <div className="drawio-editor-head">
        <div>
          <strong>专业画布</strong>
          <span>由 Draw.io 提供，支持完整图形库、连线与格式设置</span>
        </div>
        <div className="drawio-editor-actions">
          <button type="button" className="uml-tool-btn" onClick={() => requestExport('png')} disabled={exporting !== null}>
            导出 PNG
          </button>
          <button type="button" className="uml-tool-btn" onClick={() => requestExport('svg')} disabled={exporting !== null}>
            导出 SVG
          </button>
          <button type="button" className="uml-tool-btn" onClick={() => requestExport('xml')} disabled={exporting !== null}>
            导出 Draw.io XML
          </button>
        </div>
      </div>
      <iframe
        ref={iframeRef}
        className="drawio-editor-frame"
        src={embedUrl.toString()}
        title="Iris Draw.io 专业流程图"
        referrerPolicy="no-referrer"
      />
      <div className="drawio-editor-status" aria-live="polite">
        {status}
      </div>
    </section>
  );
}
