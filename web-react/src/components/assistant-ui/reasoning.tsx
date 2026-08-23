import type { ReasoningMessagePartComponent, ReasoningMessagePartProps } from "@assistant-ui/react";
import { BrainIcon, ChevronDownIcon } from "lucide-react";
import { useId, useState } from "react";

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
        <BrainIcon className="size-4" aria-hidden="true" />
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
