"use client";

import { Loader2 } from "lucide-react";

export interface SubtaskStatus {
  id: string;
  query: string;
  completed: boolean;
}

interface Props {
  stage: "planning" | "searching" | "synthesizing" | null;
  stageMessage: string;
  subtasks: SubtaskStatus[];
}

export function ProgressPanel({ stage, stageMessage, subtasks }: Props) {
  if (!stage) return null;

  const completedCount = subtasks.filter((s) => s.completed).length;

  return (
    <div className="rounded-lg border border-cyan-500/15 dark:bg-[#060d1a] bg-slate-900 font-mono p-4 space-y-3 animate-fade-in">
      {/* Stage header */}
      <div className="flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400 shrink-0" />
        <span className="text-xs text-cyan-400">{stageMessage}</span>
        {stage === "searching" && subtasks.length > 0 && (
          <span className="text-xs text-cyan-500/40 ml-auto tabular-nums">
            {completedCount}/{subtasks.length}
          </span>
        )}
      </div>

      {/* Subtask list */}
      {subtasks.length > 0 && (
        <div className="space-y-1.5 border-t border-white/5 pt-2.5">
          {subtasks.map((s) => (
            <div key={s.id} className="flex items-start gap-2.5">
              {s.completed ? (
                <span className="text-green-400 text-xs mt-0.5 shrink-0 leading-5">✓</span>
              ) : (
                <span className="text-cyan-500/40 text-xs mt-0.5 shrink-0 leading-5">›</span>
              )}
              <span
                className={`text-xs leading-5 line-clamp-1 flex-1 ${
                  s.completed ? "text-white/20" : "text-cyan-300"
                }`}
              >
                {s.query}
                {!s.completed && (
                  <span className="animate-blink inline-block ml-0.5 text-cyan-400">▋</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
