export const DRAWIO_STORAGE_KEY = 'iris_drawio_diagram_v1';
export const MAX_DRAWIO_XML_CHARS = 12 * 1024 * 1024;

export type DrawioDiagramSource = 'drawio' | 'mermaid';

export type StoredDrawioDiagram = {
  version: 1;
  xml: string;
  updatedAt: number;
  source?: DrawioDiagramSource;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function readStoredDrawioDiagram(): StoredDrawioDiagram | null {
  try {
    const raw = localStorage.getItem(DRAWIO_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.version !== 1 || typeof parsed.xml !== 'string' || parsed.xml.length > MAX_DRAWIO_XML_CHARS) return null;
    if (typeof parsed.updatedAt !== 'number' || !Number.isFinite(parsed.updatedAt)) return null;
    const source = parsed.source === 'mermaid' ? 'mermaid' : parsed.source === 'drawio' ? 'drawio' : undefined;
    return { version: 1, xml: parsed.xml, updatedAt: parsed.updatedAt, ...(source ? { source } : {}) };
  } catch {
    return null;
  }
}

export function writeStoredDrawioDiagram(diagram: StoredDrawioDiagram): boolean {
  try {
    localStorage.setItem(DRAWIO_STORAGE_KEY, JSON.stringify(diagram));
    return true;
  } catch {
    return false;
  }
}

export function hasSavedDrawioDiagram(): boolean {
  return Boolean(readStoredDrawioDiagram()?.xml.trim());
}
