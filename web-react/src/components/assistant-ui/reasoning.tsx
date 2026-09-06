import type { ReasoningMessagePartComponent, ReasoningMessagePartProps } from "@assistant-ui/react";
import { ChevronDownIcon } from "lucide-react";
import { useId, useState } from "react";

function IrisThinkingIcon({ running }: { running: boolean }) {
  return (
    <svg
      className={`iris-thinking-mark${running ? " is-running" : ""}`}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m3.25 11.5 3.5-5 3.1 3.3 4.05-5.8" />
      <path d="m10.55 14.8 2.65-3.25 3.05 1.2" />
      <circle cx="3.25" cy="11.5" r="1" fill="currentColor" stroke="none" />
      <circle cx="14" cy="4" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export const Reasoning: ReasoningMessagePartComponent = ({ text, status }: ReasoningMessagePartProps) => {
  const running = status.type === "running";
  const [open, setOpen] = useState(false);
  const regionId = useId();

  return (
    <div className="aui-reasoning iris-inline-disclosure">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left text-muted-foreground"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={() => setOpen((value) => !value)}
      >
        <IrisThinkingIcon running={running} />
        <span>{running ? "正在思考" : "思考过程"}</span>
        {running && (
          <span className="ml-1 inline-flex gap-1" aria-label="思考中">
            {[0, 1, 2].map((index) => (
              <span
                key={index}
                className="size-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none"
                style={{ animationDelay: `${index * 160}ms` }}
              />
            ))}
          </span>
        )}
        <ChevronDownIcon
          className={`ml-auto size-4 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && text && (
        <div id={regionId} role="region" className="iris-inline-disclosure-content whitespace-pre-wrap text-muted-foreground">
          {text}
        </div>
      )}
    </div>
  );
};
