import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToolGroup } from "./tool-group";

describe("ToolGroup", () => {
  it("renders one collapsed summary and expands all tool details together", () => {
    render(<ToolGroup items={[
      { callId: "1", name: "list_directory", args: { path: "." }, argsText: '{"path":"."}', result: { files: [] }, state: "completed" },
      { callId: "2", name: "read_file", args: { path: "a.ts" }, argsText: '{"path":"a.ts"}', result: "ok", state: "completed" },
    ]} />);

    const toggle = screen.getByRole("button", { name: /已执行 2 个工具/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("list_directory")).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("list_directory")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
  });

  it("summarizes running and failed states", () => {
    const { rerender } = render(<ToolGroup items={[
      { callId: "1", name: "read_file", args: {}, argsText: "{}", state: "running" },
      { callId: "2", name: "search", args: {}, argsText: "{}", state: "running" },
    ]} />);
    expect(screen.getByRole("button", { name: "正在执行 2 个工具" })).toBeVisible();
    rerender(<ToolGroup items={[{ callId: "3", name: "exec", args: {}, argsText: "{}", result: { stderr: "bad" }, state: "failed" }]} />);
    expect(screen.getByRole("button", { name: "1 个工具执行失败" })).toBeVisible();
  });

  it("uses the terminal renderer for command results", () => {
    const { container } = render(<ToolGroup items={[
      { callId: "1", name: "powershell", args: {}, argsText: "{}", result: { command: "npm test", stdout: "157 passed", exitCode: 0 }, state: "completed" },
    ]} />);
    fireEvent.click(screen.getByRole("button", { name: "已执行 1 个工具" }));
    fireEvent.click(screen.getByText("powershell"));
    expect(container.querySelector(".iris-tool-terminal")).toBeInTheDocument();
    expect(screen.getByText("157 passed")).toBeVisible();
  });

  it("shows the active search query and completed result count", () => {
    const { rerender } = render(<ToolGroup items={[
      { callId: "search-1", name: "web_search", args: { query: "最新 AI 新闻" }, argsText: "{}", state: "running" },
    ]} />);
    expect(screen.getByRole("button", { name: "正在搜索：最新 AI 新闻" })).toBeVisible();

    rerender(<ToolGroup items={[
      { callId: "search-1", name: "web_search", args: { query: "最新 AI 新闻" }, argsText: "{}", result: [{}, {}, {}], state: "completed" },
    ]} />);
    expect(screen.getByRole("button", { name: "找到 3 个结果" })).toBeVisible();
  });

  it("shows page reading progress for parallel fetches", () => {
    render(<ToolGroup items={[
      { callId: "fetch-1", name: "fetch_page", args: { url: "https://a.example" }, argsText: "{}", result: "A", state: "completed" },
      { callId: "fetch-2", name: "fetch_page", args: { url: "https://b.example" }, argsText: "{}", state: "running" },
      { callId: "fetch-3", name: "fetch_page", args: { url: "https://c.example" }, argsText: "{}", state: "running" },
    ]} />);

    expect(screen.getByRole("button", { name: "正在读取网页 1/3" })).toBeVisible();
  });
});
