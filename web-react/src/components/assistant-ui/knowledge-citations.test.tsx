import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KnowledgeCitations } from "./knowledge-citations";

describe("KnowledgeCitations", () => {
  it("opens and highlights the citation requested from answer text", () => {
    render(<KnowledgeCitations items={[
      { index: 1, document_id: "document-1", chunk_id: "chunk-1", title: "检索设计", content: "第一条来源", score: 0.8 },
      { index: 2, document_id: "document-2", chunk_id: "chunk-2", title: "重排设计", content: "第二条来源", score: 0.9 },
    ]} />);

    fireEvent(window, new CustomEvent("iris:open-knowledge-citation", { detail: { index: 2 } }));

    expect(screen.getByText("[2] 重排设计").closest("button")).toHaveAttribute("data-active", "true");
    expect(screen.getByText("[1] 检索设计").closest("button")).toHaveAttribute("data-active", "false");
  });

  it("scrolls the requested citation card into view", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    render(<KnowledgeCitations items={[
      { index: 1, document_id: "document-1", chunk_id: "chunk-1", title: "检索设计", content: "第一条来源", score: 0.8 },
      { index: 2, document_id: "document-2", chunk_id: "chunk-2", title: "重排设计", content: "第二条来源", score: 0.9 },
    ]} />);

    fireEvent(window, new CustomEvent("iris:open-knowledge-citation", { detail: { index: 2 } }));

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" }));
  });

  it("opens only the citation group in the requested assistant message", () => {
    const { container } = render(<>
      <section className="aui-assistant-message-root"><KnowledgeCitations items={[{ index: 1, document_id: "document-1", chunk_id: "chunk-1", title: "第一条回答", content: "来源一", score: 0.8 }]} /></section>
      <section className="aui-assistant-message-root"><KnowledgeCitations items={[{ index: 1, document_id: "document-2", chunk_id: "chunk-2", title: "第二条回答", content: "来源二", score: 0.9 }]} /></section>
    </>);
    const messages = container.querySelectorAll<HTMLElement>(".aui-assistant-message-root");

    fireEvent(window, new CustomEvent("iris:open-knowledge-citation", { detail: { index: 1, messageRoot: messages[1] } }));

    expect(within(messages[0]).getByRole("button", { name: /知识库引用/ })).toHaveAttribute("aria-expanded", "false");
    expect(within(messages[1]).getByRole("button", { name: /知识库引用/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("opens the cited document at its source chunk", () => {
    const listener = vi.fn();
    window.addEventListener("iris:open-knowledge", listener);
    render(<KnowledgeCitations items={[
      { index: 1, document_id: "document-1", chunk_id: "chunk-7", title: "检索设计", content: "来源段落", location: "第 3 节", score: 0.8 },
    ]} />);

    fireEvent.click(screen.getByRole("button", { name: /知识库引用/ }));
    fireEvent.click(screen.getByText("[1] 检索设计").closest("button")!);

    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][0].detail).toEqual({ documentId: "document-1", chunkId: "chunk-7" });
    window.removeEventListener("iris:open-knowledge", listener);
  });

  it("shows the routed knowledge collection for a citation", () => {
    render(<KnowledgeCitations items={[
      { index: 1, document_id: "document-1", chunk_id: "chunk-1", title: "交付计划", content: "客户交付资料", score: 0.8, collection_name: "客户资料" },
    ]} />);

    fireEvent.click(screen.getByRole("button", { name: /知识库引用/ }));

    expect(screen.getByText("知识库：客户资料")).toBeInTheDocument();
  });
});
