import type { SourceMessagePartComponent, SourceMessagePartProps } from "@assistant-ui/react";
import { ExternalLinkIcon } from "lucide-react";

function safeSource(url: string): URL | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed : null;
  } catch {
    return null;
  }
}

export const Source: SourceMessagePartComponent = ({ url, title }: SourceMessagePartProps) => {
  const parsed = safeSource(url);
  if (!parsed) return null;

  return (
    <a
      href={parsed.href}
      target="_blank"
      rel="noreferrer noopener"
      className="iris-source-chip"
    >
      <span className="truncate">{title || parsed.hostname}</span>
      <ExternalLinkIcon className="size-3 shrink-0" aria-hidden="true" />
    </a>
  );
};
