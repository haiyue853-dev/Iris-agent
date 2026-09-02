import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BookOpenIcon, ChevronDownIcon, GlobeIcon, MicIcon, SparklesIcon } from "lucide-react";
import { listKnowledgeCollections } from "@/api/knowledge";
import { readOnlineSearchEnabled, setOnlineSearchEnabled } from "@/lib/capability-mode";
import { useIrisChat } from "./iris-chat-context";

export function PromptPreviewControls() {
  const [notice, setNotice] = useState("");
  const [onlineSearchEnabled, setOnlineSearchEnabledState] = useState(readOnlineSearchEnabled);
  const [knowledgeEnabled, setKnowledgeEnabled] = useState(() => localStorage.getItem("iris_chat_use_knowledge") === "true");
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [knowledgeMenuLeft, setKnowledgeMenuLeft] = useState(16);
  const [knowledgeMenuBottom, setKnowledgeMenuBottom] = useState(80);
  const [collections, setCollections] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedKnowledgeId, setSelectedKnowledgeId] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const [modelMenuLeft, setModelMenuLeft] = useState(16);
  const [modelMenuBottom, setModelMenuBottom] = useState(80);
  const knowledgeTriggerRef = useRef<HTMLButtonElement>(null);
  const knowledgeMenuRef = useRef<HTMLSpanElement>(null);
  const modelTriggerRef = useRef<HTMLButtonElement>(null);
  const modelMenuRef = useRef<HTMLSpanElement>(null);
  const { modelProfiles, selectedModelProfileId, activeModelProfileId, selectModelProfile, modelSelectionLocked } = useIrisChat();
  const effectiveModel = modelProfiles.find((item) => item.id === (selectedModelProfileId || activeModelProfileId));
  const preview = (name: string) => setNotice(`${name}暂未开放`);
  const toggleOnlineSearch = () => {
    const enabled = !onlineSearchEnabled;
    setOnlineSearchEnabled(enabled);
    setOnlineSearchEnabledState(enabled);
  };

  useEffect(() => {
    const update = (event: Event) => setKnowledgeEnabled(Boolean((event as CustomEvent<{ enabled: boolean }>).detail?.enabled));
    window.addEventListener("iris:knowledge-state", update);
    const updateCollections = (event: Event) => setCollections((event as CustomEvent<Array<{ id: string; name: string }>>).detail || []);
    window.addEventListener("iris:knowledge-collections", updateCollections);
    return () => { window.removeEventListener("iris:knowledge-state", update); window.removeEventListener("iris:knowledge-collections", updateCollections); };
  }, []);

  useEffect(() => { void listKnowledgeCollections().then(setCollections).catch(() => setCollections([])); }, []);

  useEffect(() => {
    const closeMenus = () => { setKnowledgeOpen(false); setModelOpen(false); };
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (knowledgeTriggerRef.current?.contains(target) || knowledgeMenuRef.current?.contains(target) || modelTriggerRef.current?.contains(target) || modelMenuRef.current?.contains(target)) return;
      closeMenus();
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    window.addEventListener("blur", closeMenus);
    return () => { document.removeEventListener("pointerdown", closeOnOutsidePointer); window.removeEventListener("blur", closeMenus); };
  }, []);

  return (
    <>
      <button type="button" className="iris-prompt-tool iris-prompt-icon-tool" aria-label="语音输入（暂未开放）" onClick={() => preview("语音输入")}><MicIcon aria-hidden="true" /></button>
      <button type="button" className={`iris-prompt-tool ${onlineSearchEnabled ? "is-online" : ""}`} aria-label="联网搜索" aria-pressed={onlineSearchEnabled} onClick={toggleOnlineSearch}><GlobeIcon aria-hidden="true" /><span>联网</span></button>
      <span className="inline-block">
        <button ref={knowledgeTriggerRef} type="button" className={`iris-prompt-tool ${knowledgeEnabled ? "is-online" : ""}`} aria-pressed={knowledgeEnabled} aria-label="选择知识库" onClick={(event) => { const rect = event.currentTarget.getBoundingClientRect(); setKnowledgeMenuLeft(rect.left); setKnowledgeMenuBottom(window.innerHeight - rect.top + 6); setModelOpen(false); setKnowledgeOpen((open) => !open); }}><BookOpenIcon aria-hidden="true" /><span>{collections.find((item) => item.id === selectedKnowledgeId)?.name || "知识库"}</span></button>
        {knowledgeOpen && createPortal(<span ref={knowledgeMenuRef} className="fixed z-[9999] w-40 border border-border/40 bg-background p-1 shadow-md" style={{ left: knowledgeMenuLeft, bottom: knowledgeMenuBottom }}>
          <button className="block w-full px-2 py-1 text-left text-xs hover:bg-accent" onClick={() => { setSelectedKnowledgeId(""); window.dispatchEvent(new Event("iris:disable-knowledge")); setKnowledgeOpen(false); }}>不开启知识库</button>
          <button className="block w-full px-2 py-1 text-left text-xs hover:bg-accent" onClick={() => { setSelectedKnowledgeId(""); window.dispatchEvent(new CustomEvent("iris:select-knowledge", { detail: { id: "" } })); setKnowledgeOpen(false); }}>全部知识库</button>
          {collections.map((item) => <button key={item.id} className="block w-full px-2 py-1 text-left text-xs hover:bg-accent" onClick={() => { setSelectedKnowledgeId(item.id); window.dispatchEvent(new CustomEvent("iris:select-knowledge", { detail: { id: item.id } })); setKnowledgeOpen(false); }}>{item.name}</button>)}
        </span>, document.body)}
      </span>
      <span className="inline-block">
        <button ref={modelTriggerRef} type="button" className="iris-prompt-tool iris-model-preview" aria-label="选择模型" aria-expanded={modelOpen} disabled={modelSelectionLocked} onClick={(event) => { const rect = event.currentTarget.getBoundingClientRect(); setModelMenuLeft(Math.max(8, Math.min(rect.left, window.innerWidth - 264))); setModelMenuBottom(window.innerHeight - rect.top + 6); setKnowledgeOpen(false); setModelOpen((open) => !open); }}><SparklesIcon aria-hidden="true" /><span className="iris-model-label">{effectiveModel?.model || "当前模型"}</span><ChevronDownIcon className={`transition-transform ${modelOpen ? "rotate-180" : ""}`} aria-hidden="true" /></button>
        {modelOpen && createPortal(<span ref={modelMenuRef} className="fixed z-[9999] w-64 border border-border/40 bg-background p-1 shadow-md" style={{ left: modelMenuLeft, bottom: modelMenuBottom }}>
          {modelProfiles.map((item) => <button key={item.id} className="block w-full px-2 py-2 text-left text-sm hover:bg-accent" onClick={() => { void selectModelProfile(item.id); setModelOpen(false); }}>{item.model}</button>)}
        </span>, document.body)}
      </span>
      <span className="sr-only" role="status" aria-live="polite">{notice}</span>
    </>
  );
}
