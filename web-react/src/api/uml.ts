import type { UmlAnalyzeResult, UmlDiagramType } from '../types';

const API_BASE = 'http://localhost:8000';

async function checked(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || `请求失败 (${response.status})`);
  }
  return response;
}

/** 让 AI 分析需求/代码并生成 Mermaid 流程图 */
export async function analyzeUml(prompt: string, diagramType: UmlDiagramType): Promise<UmlAnalyzeResult> {
  const response = await checked(
    await fetch(`${API_BASE}/api/uml/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, diagram_type: diagramType }),
    })
  );
  return (await response.json()) as UmlAnalyzeResult;
}
