import { CheckIcon, LoaderCircleIcon, SearchIcon, SparklesIcon, WaypointsIcon } from "lucide-react";
import type { IrisRagPipelineStage } from "@/lib/irisRuntime";

const labels = { planning: "分析问题", retrieval: "检索知识", rerank: "重排候选", generation: "生成回答" } as const;
const icons = { planning: WaypointsIcon, retrieval: SearchIcon, rerank: SearchIcon, generation: SparklesIcon } as const;
const routeLabels: Record<string, string> = { keyword: "关键词", vector: "向量", graph: "图谱", reranker: "重排" };

function stageDetail(stage: IrisRagPipelineStage): string {
  if (stage.stage === "planning" && stage.detail.mode) {
    return stage.detail.mode === "global" ? "全局关联模式" : stage.detail.mode === "precise" ? "精准检索模式" : "混合检索模式";
  }
  if (stage.stage === "retrieval" && stage.status === "completed") {
    const routes = (stage.detail.routes || []).map((route) => routeLabels[route] || route).join(" + ");
    return `${stage.detail.citations || 0} 条引用${routes ? ` · ${routes}` : ""}`;
  }
  if (stage.stage === "rerank" && stage.status === "completed") {
    return `${stage.detail.citations || 0} 条候选已重排`;
  }
  return stage.status === "running" ? "处理中…" : "已完成";
}

export function RagPipelineProgress({ stages }: { stages: IrisRagPipelineStage[] }) {
  return <section className="iris-rag-pipeline" aria-label="RAG 处理进度">
    <div className="iris-rag-pipeline-title"><SparklesIcon className="size-3.5" /><span>知识检索</span></div>
    <div className="iris-rag-pipeline-steps">{stages.map((stage) => {
      const Icon = icons[stage.stage];
      const running = stage.status === "running";
      return <div className={`iris-rag-pipeline-step ${stage.status}`} key={stage.stage} aria-label={`${labels[stage.stage]}${running ? "进行中" : "已完成"}`}>
        <span className="iris-rag-pipeline-icon">{running ? <LoaderCircleIcon className="size-3.5 animate-spin motion-reduce:animate-none" /> : stage.status === "completed" ? <CheckIcon className="size-3.5" /> : <Icon className="size-3.5" />}</span>
        <span><strong>{labels[stage.stage]}</strong><small>{stageDetail(stage)}</small></span>
      </div>;
    })}</div>
  </section>;
}
