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
    <div className="rounded-lg border dark:border-white/5 border-border overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-2.5 dark:bg-white/[0.02] bg-muted/40 hover:dark:bg-white/[0.04] hover:bg-muted/60 transition-colors text-left"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 dark:text-white/25 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 dark:text-white/25 text-muted-foreground shrink-0" />
        )}
        <span className="font-mono text-[10px] dark:text-cyan-500/50 text-cyan-600/70 shrink-0 tracking-widest uppercase">
          Q
        </span>
        <span className="text-xs dark:text-white/60 text-slate-600 truncate flex-1">
          {item.query}
        </span>
        <span className="font-mono text-[10px] dark:text-white/20 text-slate-400 shrink-0 ml-1">
          Earlier
        </span>
      </button>

      {open && (
        <div className="px-6 py-4 prose prose-sm dark:prose-invert max-w-none border-t dark:border-white/5 border-border">
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
      {/* Divider */}
      <div className="flex items-center gap-3">
        <div className="h-px flex-1 dark:bg-white/5 bg-border" />
        <span className="font-mono text-[10px] dark:text-white/25 text-slate-400 tracking-[0.2em] uppercase">
          Prior Research
        </span>
        <div className="h-px flex-1 dark:bg-white/5 bg-border" />
      </div>

      {items.map((item, i) => (
        <HistoryEntry
          key={i}
          item={item}
          defaultOpen={i === items.length - 1}
        />
      ))}
    </div>
  );
}
