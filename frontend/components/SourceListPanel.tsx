"use client";

import { ExternalLink } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SourceEntry } from "@/lib/api";

interface Props {
  sources: SourceEntry[];
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function formatDate(d: string): string {
  if (!d) return "";
  try {
    return new Date(d).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return d;
  }
}

export function SourceListPanel({ sources }: Props) {
  return (
    <div className="flex flex-col h-full">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 pt-4 pb-3 shrink-0 border-b dark:border-white/5 border-border">
        <h2 className="font-mono text-[10px] tracking-[0.2em] uppercase dark:text-cyan-500/60 text-cyan-600/80">
          Sources
        </h2>
        {sources.length > 0 && (
          <span className="font-mono text-[10px] dark:bg-cyan-500/10 bg-cyan-50 dark:text-cyan-400 text-cyan-600 border dark:border-cyan-500/20 border-cyan-200 rounded px-1.5 py-0.5 tabular-nums">
            {sources.length}
          </span>
        )}
      </div>

      {sources.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <p className="font-mono text-[10px] dark:text-white/20 text-slate-400 text-center tracking-wide">
            Sources will appear here<br />as the search runs.
          </p>
        </div>
      ) : (
        <ScrollArea className="flex-1 px-3 pb-3 pt-2">
          <div className="space-y-2">
            {sources.map((s, i) => (
              <a
                key={`${s.url}-${i}`}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block group rounded-md border dark:border-white/5 border-slate-100 dark:bg-white/[0.02] bg-white p-2.5 hover:dark:border-cyan-500/35 hover:border-cyan-200 hover:dark:shadow-[0_0_10px_2px_rgb(6_182_212/0.10)] transition-all duration-200"
              >
                <div className="flex items-start gap-2">
                  <ExternalLink className="h-3 w-3 mt-0.5 dark:text-white/20 text-slate-300 group-hover:dark:text-cyan-400 group-hover:text-cyan-500 shrink-0 transition-colors" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium leading-snug truncate dark:text-white/70 text-slate-700 group-hover:dark:text-white group-hover:text-slate-900 transition-colors">
                      {s.title || hostname(s.url)}
                    </p>
                    <p className="font-mono text-[10px] dark:text-cyan-400/70 text-cyan-600/80 truncate mt-0.5">
                      {hostname(s.url)}
                    </p>
                    {s.publish_date && (
                      <p className="font-mono text-[10px] dark:text-white/25 text-slate-400 mt-0.5">
                        {formatDate(s.publish_date)}
                      </p>
                    )}
                  </div>
                </div>
              </a>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
