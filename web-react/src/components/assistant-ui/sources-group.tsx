import { useId, useState } from "react";
import { ChevronDownIcon, ExternalLinkIcon, LinkIcon } from "lucide-react";
import type { IrisSourcesGroupResult } from "@/lib/irisRuntime";

function safeUrl(url: string): URL | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed : null;
  } catch {
    return null;
  }
}

export function SourcesGroup({ items }: { items: IrisSourcesGroupResult["items"] }) {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  const label = `共 ${items.length} 个来源`;

  return (
    <div className="iris-sources-group">
      <button type="button" aria-expanded={open} aria-controls={regionId} aria-label={label} onClick={() => setOpen((value) => !value)}>
        <LinkIcon className="size-3.5" aria-hidden="true" />
        <span>{label}</span>
        <ChevronDownIcon className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>
      {open && (
        <div id={regionId} className="iris-sources-list">
          {items.map((item) => {
            const parsed = safeUrl(item.url);
            if (!parsed) return null;
            return <a key={item.id} href={parsed.href} target="_blank" rel="noreferrer noopener"><span>{item.title || parsed.hostname}</span><ExternalLinkIcon className="size-3" aria-hidden="true" /></a>;
          })}
        </div>
      )}
    </div>
  );
}
