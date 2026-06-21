"use client";

import { ExternalLink } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
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
      <div className="flex items-center justify-between px-4 pt-4 pb-2 shrink-0 border-b border-border bg-accent/30">
        <h2 className="text-sm font-semibold text-accent-foreground">Sources</h2>
        {sources.length > 0 && (
          <Badge variant="secondary" className="text-xs">
            {sources.length}
          </Badge>
        )}
      </div>

      {sources.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <p className="text-xs text-muted-foreground text-center">
            Sources will appear here as the search runs.
          </p>
        </div>
      ) : (
        <ScrollArea className="flex-1 px-4 pb-4">
          <div className="space-y-3">
            {sources.map((s, i) => (
              <a
                key={`${s.url}-${i}`}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block group rounded-md border border-border bg-background p-2.5 hover:bg-accent/60 hover:border-primary/30 transition-colors"
              >
                <div className="flex items-start gap-2">
                  <ExternalLink className="h-3.5 w-3.5 mt-0.5 text-muted-foreground group-hover:text-primary shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium leading-snug truncate text-foreground group-hover:text-primary">
                      {s.title || hostname(s.url)}
                    </p>
                    <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                      {hostname(s.url)}
                    </p>
                    {s.publish_date && (
                      <p className="text-[10px] text-muted-foreground mt-0.5">
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
