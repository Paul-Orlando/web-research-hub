const BASE_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

if (!BASE_URL) {
  console.error("NEXT_PUBLIC_API_URL is not set — API calls will fail");
}

export type DepthMode = "quick" | "standard" | "deep";

export interface SourceEntry {
  url: string;
  title: string;
  publish_date: string;
}

export interface HistoryEntry {
  query: string;
  report: string;
}

export interface SubtaskInfo {
  id: string;
  query: string;
  source_type: string;
  priority: number;
}

// ── SSE event payloads ────────────────────────────────────────────────────────

export interface StageEvent {
  stage: "planning" | "searching" | "synthesizing";
  message: string;
}

export interface SubtasksEvent {
  count: number;
  subtasks: SubtaskInfo[];
}

export interface SubtaskCompleteEvent {
  id: string;
  query: string;
  sources: { url: string; publish_date: string; title: string }[];
  index: number;
  total: number;
}

export interface ReportEvent {
  markdown: string;
}

export interface ErrorEvent {
  message: string;
}

export type SSECallbacks = {
  onStage?: (e: StageEvent) => void;
  onSubtasks?: (e: SubtasksEvent) => void;
  onSubtaskComplete?: (e: SubtaskCompleteEvent) => void;
  onReport?: (e: ReportEvent) => void;
  onDone?: () => void;
  onError?: (e: ErrorEvent) => void;
};

// ── stream ────────────────────────────────────────────────────────────────────

export async function startResearch(
  query: string,
  depthMode: DepthMode,
  sessionId: string,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE_URL}/research`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    },
    body: JSON.stringify({
      query,
      depth_mode: depthMode,
      session_id: sessionId,
    }),
    signal,
  });

  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  if (!response.body) throw new Error("No response body");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Normalise line endings then split on SSE event boundaries
    const normalised = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const chunks = normalised.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      if (!chunk.trim()) continue;

      let eventType = "message";
      let dataStr = "";

      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr = line.slice(5).trim();
      }

      if (!dataStr) continue;

      console.log("[SSE]", eventType, dataStr.slice(0, 120));

      try {
        const data = JSON.parse(dataStr);
        switch (eventType) {
          case "stage":
            callbacks.onStage?.(data as StageEvent);
            break;
          case "subtasks":
            callbacks.onSubtasks?.(data as SubtasksEvent);
            break;
          case "subtask_complete":
            callbacks.onSubtaskComplete?.(data as SubtaskCompleteEvent);
            break;
          case "report":
            callbacks.onReport?.(data as ReportEvent);
            break;
          case "done":
            callbacks.onDone?.();
            break;
          case "error":
            callbacks.onError?.(data as ErrorEvent);
            break;
        }
      } catch {
        // Non-JSON data line — skip
      }
    }
  }
}

// ── REST helpers ──────────────────────────────────────────────────────────────

export async function getSources(sessionId: string): Promise<SourceEntry[]> {
  const res = await fetch(`${BASE_URL}/session/${sessionId}/sources`);
  if (!res.ok) return [];
  return res.json();
}

export async function getHistory(sessionId: string): Promise<HistoryEntry[]> {
  const res = await fetch(`${BASE_URL}/session/${sessionId}/history`);
  if (!res.ok) return [];
  return res.json();
}

export function downloadReport(
  sessionId: string,
  format: "md" | "pdf" | "docx",
): void {
  window.open(`${BASE_URL}/download-report/${sessionId}/${format}`, "_blank");
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${BASE_URL}/session/${sessionId}`, { method: "DELETE" });
}
