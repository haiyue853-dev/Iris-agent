import { describe, expect, it } from "vitest";

import { displayBranchPosition } from "./thread";

describe("displayBranchPosition", () => {
  it("uses assistant-ui's already one-based branch number", () => {
    expect(displayBranchPosition(0)).toBe(0);
  });
});
