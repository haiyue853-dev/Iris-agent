import type { InterviewKnowledgeItem } from '../types';

export async function listInterviewKnowledge(): Promise<InterviewKnowledgeItem[]> {
  const response = await fetch('http://localhost:8000/api/interview-knowledge');
  if (!response.ok) throw new Error('无法加载面试知识库，请确认后端服务已启动。');
  return (await response.json() as { items: InterviewKnowledgeItem[] }).items;
}
