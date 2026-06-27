"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
    <div className="rounded-lg border dark:border-white/5 border-border dark:bg-[#0b1020] bg-white overflow-hidden animate-fade-in">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b dark:border-white/5 border-border dark:bg-white/[0.01] bg-slate-50/80">
        <span className="font-mono text-[10px] tracking-[0.2em] uppercase dark:text-white/30 text-slate-400 mr-auto">
          Report
        </span>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 font-mono text-[11px] px-2.5 py-1 rounded-md dark:text-white/40 text-slate-500 hover:dark:text-white/70 hover:text-slate-700 hover:dark:bg-white/5 hover:bg-slate-100 transition-colors"
        >
          {copied ? (
            <Check className="h-3 w-3 text-green-400" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
          {copied ? "Copied" : "Copy"}
        </button>

        <Separator orientation="vertical" className="h-4 dark:bg-white/8" />

        <div className="flex gap-1">
          {(["md", "pdf", "docx"] as const).map((fmt) => (
            <button
              key={fmt}
              onClick={() => downloadReport(sessionId, fmt)}
              className="flex items-center gap-1 font-mono text-[11px] px-2.5 py-1 rounded-md border dark:border-white/8 border-slate-200 dark:text-white/40 text-slate-500 hover:dark:border-blue-500/40 hover:border-blue-300 hover:dark:text-blue-400 hover:text-blue-500 hover:dark:bg-blue-500/5 hover:bg-blue-50 transition-all duration-150"
            >
              <FileDown className="h-3 w-3" />
              {fmt.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-5 prose prose-sm dark:prose-invert max-w-none dark:prose-headings:text-white prose-headings:text-slate-800">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="border-l-2 border-cyan-500 pl-3 not-prose text-lg font-semibold dark:text-white text-slate-800 mt-6 mb-3">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="border-l-2 border-cyan-500/70 pl-3 not-prose text-base font-semibold dark:text-white/90 text-slate-700 mt-5 mb-2.5">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="border-l-2 border-cyan-500/40 pl-3 not-prose text-sm font-semibold dark:text-white/80 text-slate-600 mt-4 mb-2">
                {children}
              </h3>
            ),
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 dark:bg-blue-500/10 bg-blue-50 dark:border-blue-500/20 border-blue-200 border rounded-full px-2 py-0 text-[11px] dark:text-blue-400 text-blue-600 no-underline hover:dark:bg-blue-500/20 hover:bg-blue-100 transition-colors"
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
