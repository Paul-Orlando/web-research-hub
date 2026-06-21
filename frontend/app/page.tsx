"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { DepthToggle } from "@/components/DepthToggle";
import { SearchBar } from "@/components/SearchBar";
import { ClearButton } from "@/components/ClearButton";
import { ProgressPanel, SubtaskStatus } from "@/components/ProgressPanel";
import { SourceListPanel } from "@/components/SourceListPanel";
import { ReportDisplay } from "@/components/ReportDisplay";
import { ConversationHistory, HistoryItem } from "@/components/ConversationHistory";
import {
  startResearch,
  deleteSession,
  DepthMode,
  SourceEntry,
} from "@/lib/api";

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "";
  const stored = localStorage.getItem("research_session_id");
  if (stored) return stored;
  const id = crypto.randomUUID();
  localStorage.setItem("research_session_id", id);
  return id;
}

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [depthMode, setDepthMode] = useState<DepthMode>("standard");
  const [isStreaming, setIsStreaming] = useState(false);

  const [stage, setStage] = useState<"planning" | "searching" | "synthesizing" | null>(null);
  const [stageMessage, setStageMessage] = useState("");
  const [subtasks, setSubtasks] = useState<SubtaskStatus[]>([]);

  const [sources, setSources] = useState<SourceEntry[]>([]);
  const [currentReport, setCurrentReport] = useState("");
  const [currentQuery, setCurrentQuery] = useState("");
  const [streamError, setStreamError] = useState("");

  const [conversationHistory, setConversationHistory] = useState<HistoryItem[]>([]);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setSessionId(getOrCreateSessionId());
  }, []);

  const handleSearch = useCallback(
    async (query: string) => {
      if (!sessionId || isStreaming) return;

      if (currentReport && currentQuery) {
        setConversationHistory((prev) => [
          ...prev,
          { query: currentQuery, report: currentReport },
        ]);
      }

      setCurrentQuery(query);
      setIsStreaming(true);
      setCurrentReport("");
      setSources([]);
      setSubtasks([]);
      setStage(null);
      setStageMessage("");
      setStreamError("");

      const ac = new AbortController();
      abortRef.current = ac;

      try {
        await startResearch(
          query,
          depthMode,
          sessionId,
          {
            onStage: (e) => {
              setStage(e.stage);
              setStageMessage(e.message);
            },
            onSubtasks: (e) => {
              setSubtasks(
                e.subtasks.map((s) => ({
                  id: s.id,
                  query: s.query,
                  completed: false,
                }))
              );
            },
            onSubtaskComplete: (e) => {
              setSubtasks((prev) =>
                prev.map((s) => (s.id === e.id ? { ...s, completed: true } : s))
              );
              const incoming: SourceEntry[] = e.sources
                .filter((s) => s.url)
                .map((s) => ({
                  url: s.url,
                  title: s.title || "",
                  publish_date: s.publish_date || "",
                }));
              setSources((prev) => {
                const seen = new Set(prev.map((s) => s.url));
                return [...prev, ...incoming.filter((s) => !seen.has(s.url))];
              });
            },
            onReport: (e) => {
              setCurrentReport(e.markdown);
            },
            onDone: () => {
              setIsStreaming(false);
              setStage(null);
            },
            onError: (e) => {
              console.error("Stream error:", e.message);
              setStreamError(e.message);
              setIsStreaming(false);
              setStage(null);
            },
          },
          ac.signal
        );
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          console.error(err);
          setStreamError(err.message);
        }
        setIsStreaming(false);
        setStage(null);
      }
    },
    [sessionId, depthMode, isStreaming, currentReport, currentQuery]
  );

  const handleClear = useCallback(async () => {
    abortRef.current?.abort();
    if (sessionId) {
      await deleteSession(sessionId).catch(() => {});
    }
    const newId = crypto.randomUUID();
    localStorage.setItem("research_session_id", newId);
    setSessionId(newId);
    setCurrentReport("");
    setCurrentQuery("");
    setSources([]);
    setSubtasks([]);
    setConversationHistory([]);
    setStage(null);
    setStageMessage("");
    setIsStreaming(false);
  }, [sessionId]);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-border sticky top-0 z-10 bg-gradient-to-r from-primary via-[oklch(0.52_0.24_290)] to-[oklch(0.58_0.2_195)] backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-3">
          <div className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-white/20 flex items-center justify-center shadow-sm">
              <span className="text-white text-xs font-bold">R</span>
            </div>
            <span className="font-semibold text-sm text-white tracking-wide">
              Web Research Agent
            </span>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-4 py-6 flex gap-6">
        {/* Main column */}
        <main className="flex-1 min-w-0 flex flex-col gap-5">
          {conversationHistory.length > 0 && (
            <ConversationHistory items={conversationHistory} />
          )}

          {/* Input area */}
          <div className="flex flex-col gap-2.5">
            <DepthToggle
              value={depthMode}
              onChange={setDepthMode}
              disabled={isStreaming}
            />
            <div className="flex gap-2 items-end">
              <SearchBar onSearch={handleSearch} disabled={isStreaming} />
              <ClearButton onClick={handleClear} />
            </div>
          </div>

          {streamError && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              <strong>Error:</strong> {streamError}
            </div>
          )}

          {isStreaming && (
            <ProgressPanel
              stage={stage}
              stageMessage={stageMessage}
              subtasks={subtasks}
            />
          )}

          {currentReport && sessionId && (
            <ReportDisplay markdown={currentReport} sessionId={sessionId} />
          )}
        </main>

        {/* Sources sidebar */}
        <aside className="w-72 xl:w-80 shrink-0 hidden md:flex flex-col rounded-lg border border-border bg-background sticky top-[72px] h-[calc(100vh-88px)] overflow-hidden">
          <SourceListPanel sources={sources} />
        </aside>
      </div>

      {/* Mobile sources drawer */}
      {sources.length > 0 && (
        <div className="md:hidden border-t border-border bg-background">
          <details className="group">
            <summary className="flex items-center justify-between px-4 py-3 cursor-pointer list-none">
              <span className="text-sm font-semibold">
                Sources ({sources.length})
              </span>
              <span className="text-xs text-muted-foreground group-open:hidden">
                Show
              </span>
              <span className="text-xs text-muted-foreground hidden group-open:block">
                Hide
              </span>
            </summary>
            <div className="max-h-64 overflow-y-auto">
              <SourceListPanel sources={sources} />
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
