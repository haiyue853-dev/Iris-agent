import type { InterviewCollectionItem, InterviewCollectionPreview, InterviewKnowledgeItem, InterviewReviewState } from '../types';

async function responseError(response: Response, fallback: string): Promise<Error> {
  try {
    const value = await response.json() as { detail?: { message?: string } };
    return new Error(value.detail?.message || fallback);
  } catch {
    return new Error(fallback);
  }
}

export async function listInterviewKnowledge(): Promise<InterviewKnowledgeItem[]> {
  const response = await fetch('http://localhost:8000/api/interview-knowledge');
  if (!response.ok) throw new Error('无法加载面试知识库。');
  return (await response.json() as { items: InterviewKnowledgeItem[] }).items;
}

export async function getPracticeQuestion(topic?: string): Promise<InterviewKnowledgeItem | null> {
  const query = topic ? `?topic=${encodeURIComponent(topic)}` : '';
  const response = await fetch(`http://localhost:8000/api/interview-knowledge/practice${query}`);
  if (!response.ok) throw new Error('无法获取复习题目。');
  return (await response.json() as { item: InterviewKnowledgeItem | null }).item;
}

export async function reviewInterviewQuestion(id: string, reviewState: InterviewReviewState): Promise<InterviewKnowledgeItem> {
  const response = await fetch(`http://localhost:8000/api/interview-knowledge/${id}/review`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ review_state: reviewState }),
  });
  if (!response.ok) throw new Error('无法保存复习状态。');
  return (await response.json() as { item: InterviewKnowledgeItem }).item;
}

export async function previewInterviewCollection(topic: string): Promise<InterviewCollectionPreview> {
  const response = await fetch('http://localhost:8000/api/interview-knowledge/collection-preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, max_sources: 3, max_items_per_source: 10 }),
  });
  if (!response.ok) throw await responseError(response, '无法采集面试资料。');
  return await response.json() as InterviewCollectionPreview;
}

export async function saveInterviewCollection(topic: string, items: InterviewCollectionItem[]): Promise<{ added: number; total: number }> {
  const response = await fetch('http://localhost:8000/api/interview-knowledge/collection-save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic, items }),
  });
  if (!response.ok) throw await responseError(response, '无法保存采集结果。');
  return await response.json() as { added: number; total: number };
}
