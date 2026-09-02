import { BookOpenIcon, ChevronDownIcon } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { IrisKnowledgeCitationsResult } from "@/lib/irisRuntime";

const score = (value: number | null | undefined) => value == null ? "未启用" : value.toFixed(3);

export function KnowledgeCitations({ items }: { items: IrisKnowledgeCitationsResult["items"] }) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const citationRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const rootRef = useRef<HTMLDivElement | null>(null);
  const regionId = useId();
  useEffect(() => {
    const openCitation = (event: Event) => {
      const detail = (event as CustomEvent<{ index?: unknown; messageRoot?: Element | null }>).detail;
      const requestedIndex = detail?.index;
      if (detail?.messageRoot && rootRef.current?.closest(".aui-assistant-message-root") !== detail.messageRoot) return;
      if (typeof requestedIndex !== "number" || !items.some((item) => item.index === requestedIndex)) return;
      setActiveIndex(requestedIndex);
      setOpen(true);
    };
    window.addEventListener("iris:open-knowledge-citation", openCitation);
    return () => window.removeEventListener("iris:open-knowledge-citation", openCitation);
  }, [items]);
  useEffect(() => {
    if (!open || activeIndex === null) return;
    citationRefs.current[activeIndex]?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [activeIndex, open]);
  return <div ref={rootRef} className="iris-knowledge-citations"><button type="button" aria-expanded={open} aria-controls={regionId} onClick={() => setOpen((value) => !value)}><BookOpenIcon className="size-3.5" /><span>知识库引用 · {items.length}</span><ChevronDownIcon className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`} /></button>{open && <div id={regionId}>{items.map((item) => <button ref={(element) => { citationRefs.current[item.index] = element; }} className="iris-knowledge-citation" data-active={item.index === activeIndex} key={item.chunk_id} type="button" onClick={() => window.dispatchEvent(new CustomEvent("iris:open-knowledge", { detail: { documentId: item.document_id, chunkId: item.chunk_id } }))}><strong>[{item.index}] {item.title}</strong>{item.collection_name && <small>知识库：{item.collection_name}</small>}{item.location && <small>{item.location}</small>}<p>{item.content.slice(0, 180)}{item.content.length > 180 ? "…" : ""}</p><span className="iris-retrieval-scores">关键词 {score(item.keyword_score)} · 向量 {score(item.vector_score)} · 重排 {score(item.reranker_score)} · 最终 {score(item.score)}</span></button>)}</div>}</div>;
}
