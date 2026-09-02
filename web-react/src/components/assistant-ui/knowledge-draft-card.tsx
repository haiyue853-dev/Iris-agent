import { useState } from "react";
import { CheckIcon, LoaderCircleIcon, PencilIcon, XCircleIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createKnowledge } from "@/api/knowledge";
import type { IrisKnowledgeDraftResult } from "@/lib/irisRuntime";

type Props = {
  draft: IrisKnowledgeDraftResult;
  collectionId?: string;
};

type DraftFields = {
  title: string;
  content: string;
  category: string;
  sourceUrl: string;
};

export function KnowledgeDraftCard({ draft, collectionId }: Props) {
  const [savedDraft, setSavedDraft] = useState<DraftFields>({
    title: draft.title,
    content: draft.content,
    category: draft.category || "面经",
    sourceUrl: draft.source_url || "",
  });
  const [editingDraft, setEditingDraft] = useState<DraftFields>(savedDraft);
  const [editing, setEditing] = useState(false);
  const [state, setState] = useState<"pending" | "saving" | "saved" | "discarded" | "error">("pending");

  const beginEditing = () => {
    setEditingDraft(savedDraft);
    setEditing(true);
  };

  const saveEdits = () => {
    if (!editingDraft.title.trim() || !editingDraft.content.trim()) return;
    setSavedDraft(editingDraft);
    setEditing(false);
  };

  const save = async () => {
    setState("saving");
    try {
      await createKnowledge({ title: savedDraft.title, content: savedDraft.content, category: savedDraft.category, sourceUrl: savedDraft.sourceUrl || undefined, collectionId });
      setState("saved");
    } catch {
      setState("error");
    }
  };

  if (state === "saved") return <div className="iris-knowledge-draft-status"><CheckIcon className="size-4" /> 已保存到知识库</div>;
  if (state === "discarded") return <div className="iris-knowledge-draft-status"><XCircleIcon className="size-4" /> 草稿已丢弃</div>;

  return (
    <section className="iris-knowledge-draft-card" aria-label="待审核入库">
      <div className="iris-knowledge-draft-heading"><span>待审核入库</span>{!editing && <button type="button" onClick={beginEditing}><PencilIcon className="size-3.5" /> 编辑草稿</button>}</div>
      {editing ? <>
        <label>标题<input aria-label="标题" value={editingDraft.title} onChange={(event) => setEditingDraft((current) => ({ ...current, title: event.target.value }))} /></label>
        <label>分类<input aria-label="分类" value={editingDraft.category} onChange={(event) => setEditingDraft((current) => ({ ...current, category: event.target.value }))} /></label>
        <label>来源<input aria-label="来源" type="url" value={editingDraft.sourceUrl} onChange={(event) => setEditingDraft((current) => ({ ...current, sourceUrl: event.target.value }))} /></label>
        <label>正文（Markdown）<textarea aria-label="正文" value={editingDraft.content} onChange={(event) => setEditingDraft((current) => ({ ...current, content: event.target.value }))} /></label>
        <div className="iris-knowledge-draft-edit-actions"><button type="button" onClick={() => setEditing(false)}>取消编辑</button><button type="button" onClick={saveEdits} disabled={!editingDraft.title.trim() || !editingDraft.content.trim()}>保存修改</button></div>
      </> : <div className="iris-knowledge-draft-preview">
        <h3>{savedDraft.title}</h3>
        <div className="iris-knowledge-draft-meta"><span>{savedDraft.category || "未分类"}</span>{savedDraft.sourceUrl && <a href={savedDraft.sourceUrl} target="_blank" rel="noreferrer">查看来源</a>}</div>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{savedDraft.content}</ReactMarkdown>
      </div>}
      {state === "error" && <p role="alert">入库失败，请修改后重试</p>}
      <div className="iris-knowledge-draft-actions">
        <button type="button" onClick={() => setState("discarded")} disabled={state === "saving"}>丢弃</button>
        <button type="button" onClick={() => void save()} disabled={editing || state === "saving" || !savedDraft.title.trim() || !savedDraft.content.trim()}>
          {state === "saving" ? <><LoaderCircleIcon className="size-4 animate-spin" /> 保存中</> : "确认入库"}
        </button>
      </div>
    </section>
  );
}
