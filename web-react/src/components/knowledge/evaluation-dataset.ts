import type { KnowledgeEvaluationCase } from '../../api/knowledge';

export type EvaluationDatasetFormat = 'json' | 'csv';

const CSV_COLUMNS = ['question', 'expected_title', 'relevant_document_ids', 'relevant_chunk_ids', 'expected_answer'] as const;

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

function normalizeCase(value: unknown): KnowledgeEvaluationCase | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  const question = String(row.question || '').trim();
  if (!question) return null;
  const expectedTitle = String(row.expected_title || '').trim();
  const expectedDocumentId = String(row.expected_document_id || '').trim();
  const expectedAnswer = String(row.expected_answer || '').trim();
  const relevantDocumentIds = strings(row.relevant_document_ids);
  const relevantChunkIds = strings(row.relevant_chunk_ids);
  return {
    question,
    ...(expectedTitle ? { expected_title: expectedTitle } : {}),
    ...(expectedDocumentId ? { expected_document_id: expectedDocumentId } : {}),
    ...(relevantDocumentIds.length ? { relevant_document_ids: relevantDocumentIds } : {}),
    ...(relevantChunkIds.length ? { relevant_chunk_ids: relevantChunkIds } : {}),
    ...(expectedAnswer ? { expected_answer: expectedAnswer } : {}),
  };
}

function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

function parseCsvRows(source: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quoted) {
      if (char === '"' && source[index + 1] === '"') { cell += '"'; index += 1; }
      else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') { row.push(cell); cell = ''; }
    else if (char === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (char !== '\r') cell += char;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

function parseCsv(source: string): KnowledgeEvaluationCase[] {
  const [header = [], ...rows] = parseCsvRows(source.replace(/^\uFEFF/, ''));
  const indexes = new Map(header.map((name, index) => [name.trim(), index]));
  return rows.map((values) => normalizeCase({
    question: values[indexes.get('question') ?? -1],
    expected_title: values[indexes.get('expected_title') ?? -1],
    relevant_document_ids: (values[indexes.get('relevant_document_ids') ?? -1] || '').split('|').filter(Boolean),
    relevant_chunk_ids: (values[indexes.get('relevant_chunk_ids') ?? -1] || '').split('|').filter(Boolean),
    expected_answer: values[indexes.get('expected_answer') ?? -1],
  })).filter((item): item is KnowledgeEvaluationCase => item !== null);
}

export function serializeEvaluationDataset(cases: KnowledgeEvaluationCase[], format: EvaluationDatasetFormat): string {
  const normalized = cases.map(normalizeCase).filter((item): item is KnowledgeEvaluationCase => item !== null);
  if (format === 'json') return JSON.stringify({ version: 1, cases: normalized }, null, 2);
  const rows = normalized.map((item) => [item.question, item.expected_title || '', (item.relevant_document_ids || []).join('|'),
    (item.relevant_chunk_ids || []).join('|'), item.expected_answer || ''].map(csvCell).join(','));
  return [CSV_COLUMNS.join(','), ...rows].join('\r\n');
}

export function parseEvaluationDataset(source: string, fileName = ''): KnowledgeEvaluationCase[] {
  let cases: KnowledgeEvaluationCase[];
  if (fileName.toLowerCase().endsWith('.json') || /^[\s\uFEFF]*[\[{]/.test(source)) {
    let decoded: unknown;
    try { decoded = JSON.parse(source.replace(/^\uFEFF/, '')); }
    catch { throw new Error('评测集 JSON 格式无效'); }
    const values = Array.isArray(decoded) ? decoded : (decoded as { cases?: unknown[] } | null)?.cases;
    cases = Array.isArray(values) ? values.map(normalizeCase).filter((item): item is KnowledgeEvaluationCase => item !== null) : [];
  } else cases = parseCsv(source);
  if (!cases.length) throw new Error('评测集没有有效问题');
  return cases.slice(0, 200);
}
