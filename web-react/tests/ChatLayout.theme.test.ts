import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("chat layout CSS layering", () => {
  const indexCss = readFileSync(resolve("src/index.css"), "utf8");
  const appCss = readFileSync(resolve("src/App.css"), "utf8");
  const threadSource = readFileSync(
    resolve("src/components/assistant-ui/thread.tsx"),
    "utf8",
  );

  it("keeps the global reset inside the Tailwind base layer", () => {
    expect(indexCss).toMatch(/@layer base\s*\{[\s\S]*\*\s*,[\s\S]*\*::before/);
    expect(appCss).not.toMatch(/^\s*\*\s*\{/m);
  });

  it("allows the main shell to shrink without horizontal overflow", () => {
    expect(appCss).toMatch(/\.main-content\s*\{[\s\S]*?min-width:\s*0\s*;/);
  });

  it("centers the composer only while the thread is empty", () => {
    expect(threadSource).toContain("aui-thread-empty-composer");
    expect(threadSource).toContain("aui-thread-active-composer");
    expect(threadSource).toMatch(
      /condition=\{\(\{ thread \}\) => thread\.isEmpty\}[\s\S]*aui-thread-empty-composer[\s\S]*<Composer \/>/,
    );
    expect(threadSource).toMatch(
      /condition=\{\(\{ thread \}\) => !thread\.isEmpty\}[\s\S]*aui-thread-active-composer[\s\S]*<Composer \/>/,
    );
  });

  it("does not render the English starter suggestions", () => {
    expect(threadSource).not.toContain("SUGGESTIONS");
    expect(threadSource).not.toContain("ThreadSuggestions");
    expect(threadSource).not.toContain("What's the weather");
    expect(threadSource).not.toContain("Explain React hooks");
  });

  it("does not let content sizing collapse a short message input", () => {
    expect(threadSource).not.toContain("field-sizing-content");
  });

  it("pins the composer input to the full prompt width", () => {
    expect(appCss).toMatch(/\.iris-prompt-body\s+\.aui-composer-input\s*\{[\s\S]*?display:\s*block[\s\S]*?width:\s*100%/);
  });

  it("connects chat auto-follow to viewport scrolling and submission", () => {
    expect(threadSource).toContain(
      'import { useChatAutoFollow } from "@/components/assistant-ui/use-chat-auto-follow";',
    );
    expect(threadSource).toContain("const autoFollow = useChatAutoFollow();");
    expect(threadSource).toMatch(
      /<ThreadPrimitive\.Viewport[\s\S]*?ref=\{autoFollow\.viewportRef\}[\s\S]*?onScroll=\{autoFollow\.onScroll\}[\s\S]*?onSubmitCapture=\{autoFollow\.resume\}/,
    );
  });

  it("keeps streaming auto-follow scrolling immediate", () => {
    expect(threadSource).toMatch(
      /<ThreadPrimitive\.Viewport[\s\S]*?className="[^"]*iris-chat-viewport[^"]*"/,
    );
    expect(threadSource).not.toMatch(
      /<ThreadPrimitive\.Viewport[\s\S]*?className="[^"]*scroll-smooth[^"]*"/,
    );
  });

  it("resumes auto-follow when the scroll-to-bottom button is clicked", () => {
    expect(threadSource).toContain(
      "<ThreadScrollToBottom onResume={autoFollow.resume} />",
    );
    expect(threadSource).toContain(
      "const ThreadScrollToBottom: FC<{ onResume: () => void }> = ({ onResume }) =>",
    );
    expect(threadSource).toMatch(
      /<TooltipIconButton[\s\S]*?onClick=\{onResume\}[\s\S]*?>[\s\S]*?<ArrowDownIcon/,
    );
  });

  it("sizes short user bubbles from their text instead of the grid minimum", () => {
    expect(threadSource).toContain("grid-cols-1");
    expect(threadSource).not.toContain("grid-cols-[minmax(72px,1fr)_auto]");
    expect(threadSource).toContain("aui-user-message-content-wrapper relative col-start-1");
    expect(appCss).toMatch(/\.aui-user-message-content-wrapper\s*\{[\s\S]*?justify-self:\s*end[\s\S]*?max-width:\s*min\(80%,\s*620px\)/);
    expect(appCss).toMatch(/\.iris-user-message-content\s*\{[\s\S]*?width:\s*fit-content[\s\S]*?max-width:\s*100%/);
  });

  it("defines the neutral application shell and chat surface", () => {
    expect(appCss).toContain(".iris-app-shell");
    expect(appCss).toContain(".iris-main-surface");
    expect(appCss).toContain("background: var(--aui-page)");
  });

  it("defines the AI Elements conversation and prompt surfaces", () => {
    expect(threadSource).toContain("iris-conversation");
    expect(threadSource).toContain("iris-chat-welcome");
    expect(threadSource).toContain("iris-prompt-input");
    expect(threadSource).toContain('aria-label="消息输入框"');
    expect(appCss).toContain(".iris-composer-dock");
    expect(appCss).toContain(".iris-prompt-header");
    expect(appCss).toContain(".iris-prompt-footer");
    expect(appCss).toContain(".iris-streaming-cursor");
    expect(appCss).toContain(".iris-suggestions");
    expect(appCss).toContain("@media (max-width: 720px)");
  });
});
