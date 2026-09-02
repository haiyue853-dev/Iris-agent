"use client";

import "@assistant-ui/react-markdown/styles/dot.css";

import {
  type CodeHeaderProps,
  MarkdownTextPrimitive,
  unstable_memoizeMarkdownComponents as memoizeMarkdownComponents,
  useIsMarkdownCodeBlock,
} from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { type ComponentPropsWithoutRef, type FC, memo, useState } from "react";
import { CheckIcon, CopyIcon, DownloadIcon } from "lucide-react";

import {
  ArtifactAction,
  ArtifactActions,
} from "@/components/ui/artifact";
import { cn } from "@/lib/ui/cn";

const MarkdownTextImpl = () => {
  return (
    <MarkdownTextPrimitive
      remarkPlugins={[remarkGfm, remarkCitationLinks]}
      className="aui-md"
      components={defaultComponents}
    />
  );
};

export const MarkdownText = memo(MarkdownTextImpl);

type MarkdownNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
};

const citationMarker = /\[([1-9]\d*)\]/g;

export function remarkCitationLinks() {
  return (tree: MarkdownNode) => {
    const replaceMarkers = (nodes: MarkdownNode[]) => {
      for (let index = 0; index < nodes.length; index += 1) {
        const node = nodes[index];
        if (node.type === "text" && node.value) {
          citationMarker.lastIndex = 0;
          const fragments: MarkdownNode[] = [];
          let cursor = 0;
          for (let match = citationMarker.exec(node.value); match; match = citationMarker.exec(node.value)) {
            if (match.index > cursor) fragments.push({ type: "text", value: node.value.slice(cursor, match.index) });
            fragments.push({ type: "link", url: `#iris-citation-${match[1]}`, children: [{ type: "text", value: match[0] }] });
            cursor = match.index + match[0].length;
          }
          if (fragments.length) {
            if (cursor < node.value.length) fragments.push({ type: "text", value: node.value.slice(cursor) });
            nodes.splice(index, 1, ...fragments);
            index += fragments.length - 1;
          }
        } else if (node.type !== "link" && node.children) {
          replaceMarkers(node.children);
        }
      }
    };
    if (tree.children) replaceMarkers(tree.children);
  };
}

const CodeHeader: FC<CodeHeaderProps> = ({ language, code }) => {
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const onCopy = () => {
    if (!code || isCopied) return;
    copyToClipboard(code);
  };

  const onDownload = () => {
    if (!code) return;
    const extension =
      language && /^[a-z0-9+#-]+$/i.test(language) ? language : "txt";
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `snippet.${extension}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="aui-code-header-root bg-muted-foreground/15 text-foreground dark:bg-muted-foreground/20 mt-4 flex items-center justify-between gap-4 rounded-t-lg px-4 py-2 text-sm font-semibold">
      <span className="aui-code-header-language lowercase [&>span]:text-xs">
        {language}
      </span>
      <ArtifactActions>
        <ArtifactAction
          icon={isCopied ? CheckIcon : CopyIcon}
          label="Copy"
          onClick={onCopy}
          tooltip="Copy to clipboard"
        />
        <ArtifactAction
          icon={DownloadIcon}
          label="Download"
          onClick={onDownload}
          tooltip="Download snippet"
        />
      </ArtifactActions>
    </div>
  );
};

const useCopyToClipboard = ({
  copiedDuration = 3000,
}: {
  copiedDuration?: number;
} = {}) => {
  const [isCopied, setIsCopied] = useState<boolean>(false);

  const copyToClipboard = (value: string) => {
    if (!value) return;

    navigator.clipboard.writeText(value).then(() => {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), copiedDuration);
    });
  };

  return { isCopied, copyToClipboard };
};

const defaultComponents = memoizeMarkdownComponents({
  h1: ({ className, ...props }) => (
    <h1
      className={cn(
        "aui-md-h1 mb-8 scroll-m-20 text-4xl font-extrabold tracking-tight last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={cn(
        "aui-md-h2 mt-8 mb-4 scroll-m-20 text-3xl font-semibold tracking-tight first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={cn(
        "aui-md-h3 mt-6 mb-4 scroll-m-20 text-2xl font-semibold tracking-tight first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      className={cn(
        "aui-md-h4 mt-6 mb-4 scroll-m-20 text-xl font-semibold tracking-tight first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h5: ({ className, ...props }) => (
    <h5
      className={cn(
        "aui-md-h5 my-4 text-lg font-semibold first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h6: ({ className, ...props }) => (
    <h6
      className={cn(
        "aui-md-h6 my-4 font-semibold first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  p: ({ className, ...props }) => (
    <p
      className={cn("aui-md-p mt-5 mb-5 first:mt-0 last:mb-0", className)}
      {...props}
    />
  ),
  a: MarkdownLink,
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn("aui-md-blockquote border-l-2 pl-6 italic", className)}
      {...props}
    />
  ),
  ul: ({ className, ...props }) => (
    <ul
      className={cn("aui-md-ul my-5 ml-6 list-disc [&>li]:mt-2", className)}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={cn("aui-md-ol my-5 ml-6 list-decimal [&>li]:mt-2", className)}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("aui-md-hr my-5 border-b", className)} {...props} />
  ),
  table: ({ className, ...props }) => (
    <table
      className={cn(
        "aui-md-table my-5 w-full border-separate border-spacing-0 overflow-y-auto",
        className,
      )}
      {...props}
    />
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn(
        "aui-md-th bg-muted px-4 py-2 text-left font-bold first:rounded-tl-lg last:rounded-tr-lg [[align=center]]:text-center [[align=right]]:text-right",
        className,
      )}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td
      className={cn(
        "aui-md-td border-b border-l px-4 py-2 text-left last:border-r [[align=center]]:text-center [[align=right]]:text-right",
        className,
      )}
      {...props}
    />
  ),
  tr: ({ className, ...props }) => (
    <tr
      className={cn(
        "aui-md-tr m-0 border-b p-0 first:border-t [&:last-child>td:first-child]:rounded-bl-lg [&:last-child>td:last-child]:rounded-br-lg",
        className,
      )}
      {...props}
    />
  ),
  sup: ({ className, ...props }) => (
    <sup
      className={cn("aui-md-sup [&>a]:text-xs [&>a]:no-underline", className)}
      {...props}
    />
  ),
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        "aui-md-pre overflow-x-auto rounded-t-none! rounded-b-lg bg-black p-4 text-white",
        className,
      )}
      {...props}
    />
  ),
  code: function Code({ className, ...props }) {
    const isCodeBlock = useIsMarkdownCodeBlock();
    return (
      <code
        className={cn(
          !isCodeBlock &&
            "aui-md-inline-code bg-muted rounded border font-semibold",
          className,
        )}
        {...props}
      />
    );
  },
  CodeHeader,
});

export function MarkdownLink({
  className,
  href,
  target,
  rel,
  ...props
}: ComponentPropsWithoutRef<"a">) {
  const citation = /^(?:iris-citation:|#iris-citation-)([1-9]\d*)$/.exec(href ?? "");
  if (citation) {
    return (
      <button
        type="button"
        className={cn("iris-inline-citation text-primary font-medium", className)}
        aria-label={`查看引用 [${citation[1]}]`}
        onClick={(event) => { const messageRoot = event.currentTarget.closest(".aui-assistant-message-root"); window.dispatchEvent(new CustomEvent("iris:open-knowledge-citation", { detail: { index: Number(citation[1]), ...(messageRoot ? { messageRoot } : {}) } })); }}
      >
        {props.children}
      </button>
    );
  }
  const external = /^https?:\/\//i.test(href ?? "");
  return (
    <a
      className={cn(
        "aui-md-a text-primary font-medium underline underline-offset-4",
        className,
      )}
      href={href}
      target={external ? "_blank" : target}
      rel={external ? "noopener noreferrer" : rel}
      {...props}
    />
  );
}
