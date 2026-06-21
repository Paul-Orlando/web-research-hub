"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronRight } from "lucide-react";

export interface HistoryItem {
  query: string;
  report: string;
}

interface Props {
  items: HistoryItem[];
}

function HistoryEntry({ item, defaultOpen }: { item: HistoryItem; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-muted/40 hover:bg-muted/60 transition-colors text-left"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <span className="text-sm font-medium truncate">{item.query}</span>
      </button>

      {open && (
        <div className="px-6 py-4 prose prose-sm dark:prose-invert max-w-none border-t border-border">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline underline-offset-2 hover:opacity-80"
                >
                  {children}
                </a>
              ),
            }}
          >
            {item.report}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export function ConversationHistory({ items }: Props) {
  if (items.length === 0) return null;

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <HistoryEntry
          key={i}
          item={item}
          // Most recent prior report open by default, older ones collapsed
          defaultOpen={i === items.length - 1}
        />
      ))}
    </div>
  );
}
