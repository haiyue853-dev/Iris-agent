import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { createKnowledge } = vi.hoisted(() => ({
  createKnowledge: vi.fn(async () => ({ id: "knowledge-1" })),
}));

vi.mock("@/api/knowledge", () => ({ createKnowledge }));

import { KnowledgeDraftCard } from "./knowledge-draft-card";

describe("KnowledgeDraftCard", () => {
  it("previews Markdown before switching to edit mode", () => {
    render(
      <KnowledgeDraftCard
        draft={{ __irisKind: "knowledge-draft", title: "初始标题", content: "## 面试问题\n\n- 第一题", category: "面经" }}
      />,
    );

    expect(screen.getByRole("heading", { name: "面试问题" })).toBeInTheDocument();
    expect(screen.queryByLabelText("正文")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "编辑草稿" }));
    expect(screen.getByLabelText("正文")).toHaveValue("## 面试问题\n\n- 第一题");
  });

  it("lets the user edit a draft before saving it to the selected collection", async () => {
    render(
      <KnowledgeDraftCard
        draft={{ __irisKind: "knowledge-draft", title: "初始标题", content: "初始正文", category: "面经", source_url: "https://example.com" }}
        collectionId="collection-team"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑草稿" }));
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "修改后的标题" } });
    fireEvent.change(screen.getByLabelText("分类"), { target: { value: "项目复盘" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    fireEvent.click(screen.getByRole("button", { name: "确认入库" }));

    await waitFor(() => expect(createKnowledge).toHaveBeenCalledWith({
      title: "修改后的标题",
      content: "初始正文",
      category: "项目复盘",
      sourceUrl: "https://example.com",
      collectionId: "collection-team",
    }));
    expect(await screen.findByText("已保存到知识库")).toBeInTheDocument();
  });
});
