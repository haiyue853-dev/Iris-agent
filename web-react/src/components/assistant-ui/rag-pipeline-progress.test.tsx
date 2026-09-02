import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { IrisRagPipelineStage } from "@/lib/irisRuntime";
import { RagPipelineProgress } from "./rag-pipeline-progress";

describe("RagPipelineProgress", () => {
  it("shows completed retrieval details and the active generation stage", () => {
    const stages = [
      { stage: "planning", status: "completed", detail: { mode: "mix" } },
      { stage: "retrieval", status: "completed", detail: { citations: 3, routes: ["keyword", "vector", "reranker"] } },
      { stage: "rerank", status: "completed", detail: { citations: 3 } },
      { stage: "generation", status: "running", detail: {} },
    ] as unknown as IrisRagPipelineStage[];
    render(<RagPipelineProgress stages={stages} />);

    expect(screen.getByText("分析问题")).toBeInTheDocument();
    expect(screen.getByText("检索知识")).toBeInTheDocument();
    expect(screen.getByText("3 条引用 · 关键词 + 向量 + 重排")).toBeInTheDocument();
    expect(screen.getByText("重排候选")).toBeInTheDocument();
    expect(screen.getByText("生成回答")).toBeInTheDocument();
    expect(screen.getByLabelText("生成回答进行中")).toBeInTheDocument();
  });
});
