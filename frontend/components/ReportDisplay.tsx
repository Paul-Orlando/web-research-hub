"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Copy, Check, FileDown } from "lucide-react";
import { downloadReport } from "@/lib/api";

interface Props {
  markdown: string;
  sessionId: string;
}

export function ReportDisplay({ markdown, sessionId }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/30">
        <span className="text-xs font-medium text-muted-foreground mr-auto">Report</span>

        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          onClick={handleCopy}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-500" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          {copied ? "Copied" : "Copy"}
        </Button>

        <Separator orientation="vertical" className="h-4" />

        <div className="flex gap-1">
          {(["md", "pdf", "docx"] as const).map((fmt) => (
            <Button
              key={fmt}
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => downloadReport(sessionId, fmt)}
            >
              <FileDown className="h-3.5 w-3.5" />
              {fmt.toUpperCase()}
            </Button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-5 prose prose-sm dark:prose-invert max-w-none">
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
          {markdown}
        </ReactMarkdown>
      </div>
    </div>
  );
}
