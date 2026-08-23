import { useState } from "react";
import { ChevronDownIcon, GlobeIcon, MicIcon, SparklesIcon } from "lucide-react";

export function PromptPreviewControls() {
  const [notice, setNotice] = useState("");
  const preview = (name: string) => setNotice(`${name}暂未开放`);

  return (
    <>
      <button type="button" className="iris-prompt-tool iris-prompt-icon-tool" aria-label="语音输入（暂未开放）" onClick={() => preview("语音输入")}><MicIcon aria-hidden="true" /></button>
      <button type="button" className="iris-prompt-tool" aria-label="联网搜索（暂未开放）" onClick={() => preview("联网搜索")}><GlobeIcon aria-hidden="true" /><span>联网</span></button>
      <button type="button" className="iris-prompt-tool iris-model-preview" aria-label="选择模型（暂未开放）" onClick={() => preview("模型选择")}><SparklesIcon aria-hidden="true" /><span className="iris-model-label">Iris Agent</span><ChevronDownIcon aria-hidden="true" /></button>
      <span className="sr-only" role="status" aria-live="polite">{notice}</span>
    </>
  );
}
