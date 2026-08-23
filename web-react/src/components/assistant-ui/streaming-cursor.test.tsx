import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StreamingCursor } from "./streaming-cursor";

describe("StreamingCursor", () => {
  it("shows only while streaming", () => {
    const { rerender } = render(<StreamingCursor running />);
    expect(screen.getByLabelText("正在生成")).toBeVisible();
    rerender(<StreamingCursor running={false} />);
    expect(screen.queryByLabelText("正在生成")).not.toBeInTheDocument();
  });
});
