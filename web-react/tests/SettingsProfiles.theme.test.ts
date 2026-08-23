import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

type LiteralColor = { color: string; red: number; green: number; blue: number };
const START_MARKER = "/* ========== 设置弹窗 ========== */";
const END_MARKER = "/* ========== 两列竖排紧凑卡片（覆盖 .aihot-item 单列横排） ========== */";

const extractDelimitedBlock = (css: string, openBrace: number, label: string) => {
  let depth = 0;
  for (let index = openBrace; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}" && --depth === 0) return css.slice(openBrace + 1, index);
  }
  throw new Error(`Missing closing brace for ${label}`);
};

const getSettingsSection = (css: string) => {
  const start = css.indexOf(START_MARKER);
  expect(start, `Missing settings theme start marker: ${START_MARKER}`).toBeGreaterThanOrEqual(0);
  const end = css.indexOf(END_MARKER, start + START_MARKER.length);
  expect(end, `Missing settings theme end marker: ${END_MARKER}`).toBeGreaterThan(start);
  return css.slice(start + START_MARKER.length, end);
};

const getRuleDeclarations = (css: string, selector: string) => {
  for (let index = 0; index < css.length;) {
    const openBrace = css.indexOf("{", index);
    if (openBrace < 0) break;
    const preludeStart = Math.max(css.lastIndexOf("}", openBrace - 1), css.lastIndexOf("{", openBrace - 1)) + 1;
    const prelude = css.slice(preludeStart, openBrace).trim();
    const body = extractDelimitedBlock(css, openBrace, prelude || selector);
    if (!prelude.startsWith("@") && prelude.split(",").some((candidate) => candidate.trim() === selector)) return body;
    index = openBrace + body.length + 2;
  }
  throw new Error(`Missing CSS rule for selector: ${selector}`);
};

const getMediaBlock = (css: string, condition: string) => {
  const header = `@media ${condition}`;
  const start = css.indexOf(header);
  expect(start, `Missing media query: ${header}`).toBeGreaterThanOrEqual(0);
  const openBrace = css.indexOf("{", start + header.length);
  expect(openBrace, `Missing opening brace for media query: ${header}`).toBeGreaterThanOrEqual(0);
  return extractDelimitedBlock(css, openBrace, header);
};

const getRuleBodies = (css: string): string[] => {
  const bodies: string[] = [];
  for (let index = 0; index < css.length;) {
    const openBrace = css.indexOf("{", index);
    if (openBrace < 0) break;
    const preludeStart = Math.max(css.lastIndexOf("}", openBrace - 1), css.lastIndexOf("{", openBrace - 1)) + 1;
    const prelude = css.slice(preludeStart, openBrace).trim();
    const body = extractDelimitedBlock(css, openBrace, prelude || "CSS rule");
    if (prelude.startsWith("@")) bodies.push(...getRuleBodies(body));
    else bodies.push(body);
    index = openBrace + body.length + 2;
  }
  return bodies;
};

const literalColorsInDeclarations = (css: string): LiteralColor[] => {
  const colors: LiteralColor[] = [];
  let sanitizedCss = css.replace(/\/\*(?:[^*]|\*(?!\/))*\*\//g, " ");
  sanitizedCss = sanitizedCss.replace(/(["'])(?:\\.|(?!\1)[^\\])*\1/g, " ").replace(/\burl\(\s*[^)]*\)/gi, " ");
  for (const match of sanitizedCss.matchAll(/(?<![\w-])#([\da-f]{3,4}|[\da-f]{6}|[\da-f]{8})(?![\da-f])/gi)) {
    const rgbHex = match[1].length <= 4 ? match[1].slice(0, 3).split("").map((digit) => digit + digit) : [match[1].slice(0, 2), match[1].slice(2, 4), match[1].slice(4, 6)];
    const [red, green, blue] = rgbHex.map((channel) => Number.parseInt(channel, 16));
    colors.push({ color: match[0], red, green, blue });
  }
  const normalizeChannel = (channel: string) => Number.parseFloat(channel) * (channel.endsWith("%") ? 2.55 : 1);
  for (const match of sanitizedCss.matchAll(/(?<![\w-])rgba?\(\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)%?)[\s,]+([+-]?(?:\d+(?:\.\d+)?|\.\d+)%?)[\s,]+([+-]?(?:\d+(?:\.\d+)?|\.\d+)%?)(?:\s*(?:,|\/)\s*[^)]*)?\)/gi)) {
    const [red, green, blue] = match.slice(1, 4).map(normalizeChannel);
    colors.push({ color: match[0], red, green, blue });
  }
  return colors;
};

const validateColorDeclarations = (css: string) => {
  const colorProperty = /(?:color|background|border|outline|box-shadow|text-shadow|fill|stroke|caret|accent)/i;
  const forbiddenFunction = /\b(?:hsl|hsla|hwb|lab|lch|oklab|oklch|color)\s*\(/i;
  const allowedKeywords = new Set(["solid", "dashed", "dotted", "none", "transparent", "currentcolor", "inherit", "initial", "unset", "auto", "inset", "outset"]);
  const rgbChannel = "[+-]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)%?";
  const rgbLiteral = new RegExp(`rgba?\\(\\s*(${rgbChannel})[\\s,]+(${rgbChannel})[\\s,]+(${rgbChannel})(?:\\s*(?:,|\\/)\\s*${rgbChannel})?\\s*\\)`, "gi");

  for (const ruleBody of getRuleBodies(css)) {
    for (const declaration of ruleBody.matchAll(/([\w-]+)\s*:\s*([^;{}]+)/g)) {
      const property = declaration[1];
      if (!colorProperty.test(property)) continue;
      const originalValue = declaration[2].trim();
    if (forbiddenFunction.test(originalValue)) throw new Error(`Unsupported color function in ${property}: ${originalValue}`);
    if (/\bvar\s*\(/i.test(originalValue)) throw new Error(`CSS variables are not allowed in ${property}: ${originalValue}`);

      let remainder = originalValue.replace(/#(?:[\da-f]{8}|[\da-f]{6}|[\da-f]{4}|[\da-f]{3})(?![\da-f])/gi, (literal) => {
        const [color] = literalColorsInDeclarations(literal);
        if (!color || Math.abs(color.red - color.green) > 1e-8 || Math.abs(color.red - color.blue) > 1e-8) throw new Error(`Non-grayscale color in ${property}: ${literal}`);
        return " ";
      });
      remainder = remainder.replace(rgbLiteral, (literal) => {
        const [color] = literalColorsInDeclarations(literal);
        if (!color || Math.abs(color.red - color.green) > 1e-8 || Math.abs(color.red - color.blue) > 1e-8) throw new Error(`Non-grayscale color in ${property}: ${literal}`);
        return " ";
      });
      if (/#|\brgba?\s*\(/i.test(remainder)) throw new Error(`Malformed or unsupported color literal in ${property}: ${originalValue}`);

      remainder = remainder.replace(/[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:%|px|rem|em|vh|vw|vmin|vmax|s|ms|deg|turn)?/gi, " ");
      remainder = remainder.replace(/[(),/]/g, " ");
      for (const identifier of remainder.match(/[a-z-]+/gi) ?? []) {
        if (!allowedKeywords.has(identifier.toLowerCase())) throw new Error(`Unknown color token in ${property}: ${identifier}`);
      }
    }
  }
};

describe("settings profiles neutral responsive theme", () => {
  const css = readFileSync(resolve("src/App.css"), "utf8");
  const settingsCss = getSettingsSection(css);

  it("uses a bounded desktop modal with a scrollable body", () => {
    const modal = getRuleDeclarations(settingsCss, ".settings-modal");
    expect(modal).toMatch(/width:\s*760px/);
    expect(modal).toMatch(/max-width:\s*calc\([^)]+\)/);
    expect(modal).toMatch(/max-height:/);
    expect(getRuleDeclarations(settingsCss, ".settings-layout")).toMatch(/overflow-y:\s*auto/);
  });

  it("sets a grayscale base text color on the modal instead of inheriting the global foreground", () => {
    const modal = getRuleDeclarations(settingsCss, ".settings-modal");
    const colorDeclaration = modal.match(/(?:^|;)\s*color\s*:\s*([^;]+)/i)?.[1].trim();
    expect(colorDeclaration).toBeDefined();
    const [color] = literalColorsInDeclarations(colorDeclaration ?? "");
    expect(color).toBeDefined();
    expect(color.red).toBe(color.green);
    expect(color.red).toBe(color.blue);
  });

  it("lays profiles and editor out in compact desktop columns", () => {
    const layout = getRuleDeclarations(settingsCss, ".settings-layout");
    expect(layout).toMatch(/display:\s*grid/);
    expect(layout).toMatch(/grid-template-columns:\s*220px\s+minmax\(0,\s*1fr\)/);
    expect(getRuleDeclarations(settingsCss, ".settings-profiles")).toMatch(/border-right:/);
    expect(settingsCss).not.toContain(".settings-profiles-layout");
    for (const unusedSelector of [".settings-label", ".settings-badge.warn", ".settings-hint"]) {
      expect(settingsCss, unusedSelector).not.toContain(unusedSelector);
    }
  });

  it("keeps full-width settings inputs inside their container", () => {
    const input = getRuleDeclarations(settingsCss, ".settings-input");
    expect(input).toMatch(/width:\s*100%/);
    expect(input).toMatch(/box-sizing:\s*border-box/);
  });

  it("makes selection, focus and disabled states explicit", () => {
    const selected = getRuleDeclarations(settingsCss, ".settings-profile.selected");
    expect(selected).toMatch(/border-color:\s*#[0-9a-f]{3,6}/i);
    expect(selected).toMatch(/background:/);
    for (const selector of [
      ".settings-close:not(:disabled):focus-visible",
      ".settings-btn:not(:disabled):focus-visible",
      ".settings-profile:not(:disabled):focus-visible",
      ".settings-input:not(:disabled):focus-visible",
    ]) expect(getRuleDeclarations(settingsCss, selector), selector).toMatch(/outline:\s*2px\s+solid\s+#(?:000|1d1d1d)/i);
    for (const selector of [".settings-btn:disabled", ".settings-profile:disabled", ".settings-close:disabled", ".settings-input:disabled"]) {
      const declarations = getRuleDeclarations(settingsCss, selector);
      expect(declarations, selector).toMatch(/opacity:/);
      expect(declarations, selector).toMatch(/background:/);
      expect(declarations, selector).toMatch(/cursor:\s*not-allowed/);
    }
  });

  it("uses only neutral feedback and danger treatments", () => {
    for (const selector of [".settings-message.ok", ".settings-message.err", ".settings-btn.danger"]) expect(getRuleDeclarations(settingsCss, selector), selector).toMatch(/border(?:-[\w-]+)?:/);
  });

  it("styles the persisted profile metadata and current marker in grayscale", () => {
    for (const selector of [".settings-profile-main", ".settings-profile-meta", ".settings-profile-status", ".settings-profile-time", ".settings-current-dot"]) {
      expect(getRuleDeclarations(settingsCss, selector), selector).toBeTruthy();
    }
    const dot = getRuleDeclarations(settingsCss, ".settings-current-dot");
    expect(dot).toMatch(/border-radius:\s*50%/);
    expect(dot).toMatch(/background:\s*#[0-9a-f]{3,6}/i);
    expect(() => validateColorDeclarations([".settings-profile-main", ".settings-profile-meta", ".settings-profile-status", ".settings-profile-time", ".settings-current-dot"].map(selector => `${selector}{${getRuleDeclarations(settingsCss, selector)}}`).join("\n"))).not.toThrow();

    const component = readFileSync(resolve("src/components/settings/SettingsModal.tsx"), "utf8");
    for (const className of ["settings-profile-main", "settings-profile-meta", "settings-profile-status", "settings-profile-time", "settings-current-dot"]) expect(component).toContain(`className="${className}"`);
  });

  it("validates every color-bearing declaration in the settings section", () => {
    expect(() => validateColorDeclarations(settingsCss)).not.toThrow();
  });

  it.each([
    ["named border color", "a { border: 1px solid red; }"],
    ["named outline color", "a { outline: 2px solid blue; }"],
    ["unsupported relative rgb", "a { background: rgb(from #fff r g b); }"],
  ])("rejects %s", (_label, sample) => {
    expect(() => validateColorDeclarations(sample)).toThrow();
  });

  it("accepts grayscale border and rgba values", () => {
    expect(() => validateColorDeclarations("a { border: 1px solid #777; box-shadow: 0 1px 2px rgba(12, 12, 12, .5); }")).not.toThrow();
  });

  it("scans hex and rgb literals without treating URLs, comments or strings as colors", () => {
    const sample = `a { color: #aaa; background: rgb(12 12 12); } /* #f00 */ b { content: "#0f0"; background: url('/#00f.svg'); }`;
    expect(literalColorsInDeclarations(sample).map(({ color }) => color)).toEqual(["#aaa", "rgb(12 12 12)"]);
  });

  it("stacks without horizontal overflow at tablet and phone widths", () => {
    const tablet = getMediaBlock(settingsCss, "(max-width: 700px)");
    expect(getRuleDeclarations(tablet, ".settings-layout")).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/);
    expect(getRuleDeclarations(tablet, ".settings-profiles")).toMatch(/overflow-x:\s*auto/);
    const phone = getMediaBlock(settingsCss, "(max-width: 480px)");
    expect(getRuleDeclarations(phone, ".settings-foot")).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/);
    expect(getRuleDeclarations(phone, ".settings-foot .settings-btn")).toMatch(/width:\s*100%/);
  });
});
