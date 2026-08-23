import { fireEvent, render, screen } from "@testing-library/react";
import { CopyIcon, DownloadIcon } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import {
  Artifact,
  ArtifactAction,
  ArtifactActions,
  ArtifactClose,
  ArtifactContent,
  ArtifactDescription,
  ArtifactHeader,
  ArtifactTitle,
} from "./artifact";

describe("Artifact", () => {
  it("renders a composed artifact with header, actions and content", () => {
    render(
      <Artifact data-testid="artifact">
        <ArtifactHeader>
          <div>
            <ArtifactTitle>快速排序实现</ArtifactTitle>
            <ArtifactDescription>刚刚更新</ArtifactDescription>
          </div>
          <ArtifactActions>
            <ArtifactAction
              icon={CopyIcon}
              label="Copy"
            />
          </ArtifactActions>
        </ArtifactHeader>
        <ArtifactContent>print("hello")</ArtifactContent>
      </Artifact>,
    );

    expect(screen.getByText("快速排序实现")).toBeInTheDocument();
    expect(screen.getByText("刚刚更新")).toBeInTheDocument();
    expect(screen.getByText(/hello/)).toBeInTheDocument();
    expect(
      screen.getAllByRole("button"),
    ).toHaveLength(1);
  });

  it("invokes handlers when actions and close are clicked", () => {
    const onCopy = vi.fn();
    const onDownload = vi.fn();
    const onClose = vi.fn();

    render(
      <Artifact>
        <ArtifactHeader>
          <ArtifactTitle>代码片段</ArtifactTitle>
          <ArtifactActions>
            <ArtifactAction
              icon={CopyIcon}
              label="Copy"
              onClick={onCopy}
            />
            <ArtifactAction
              icon={DownloadIcon}
              label="Download"
              onClick={onDownload}
            />
          </ArtifactActions>
          <ArtifactClose onClick={onClose} />
        </ArtifactHeader>
        <ArtifactContent>content</ArtifactContent>
      </Artifact>,
    );

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3); // Copy, Download, Close

    fireEvent.click(buttons[0]);
    expect(onCopy).toHaveBeenCalledTimes(1);

    fireEvent.click(buttons[1]);
    expect(onDownload).toHaveBeenCalledTimes(1);

    fireEvent.click(buttons[2]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("falls back to custom children when no icon is provided", () => {
    render(
      <ArtifactAction label="Custom" onClick={vi.fn()}>
        <span aria-hidden>⋯</span>
      </ArtifactAction>,
    );

    expect(screen.getByRole("button", { name: "Custom" })).toBeInTheDocument();
  });
});
