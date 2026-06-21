"use client";

import { CheckCircle2, Circle, Loader2 } from "lucide-react";

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
    <div className="rounded-lg border border-primary/30 bg-primary/5 border-l-4 border-l-primary p-4 space-y-3">
      {/* Current stage */}
      <div className="flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
        <span className="text-sm font-medium">{stageMessage}</span>
        {stage === "searching" && subtasks.length > 0 && (
          <span className="text-xs text-muted-foreground ml-auto">
            {completedCount}/{subtasks.length} done
          </span>
        )}
      </div>

      {/* Subtask dots — shown once we have subtask info */}
      {subtasks.length > 0 && (
        <div className="space-y-1.5">
          {subtasks.map((s) => (
            <div key={s.id} className="flex items-start gap-2">
              {s.completed ? (
                <CheckCircle2 className="h-4 w-4 text-primary mt-0.5 shrink-0" />
              ) : (
                <Circle className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
              )}
              <span
                className={`text-xs leading-5 line-clamp-1 ${
                  s.completed ? "text-muted-foreground" : "text-foreground"
                }`}
              >
                {s.query}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
