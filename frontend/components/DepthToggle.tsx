"use client";

import { DepthMode } from "@/lib/api";

interface Props {
  value: DepthMode;
  onChange: (v: DepthMode) => void;
  disabled?: boolean;
}

const MODES: { value: DepthMode; label: string; description: string }[] = [
  { value: "quick", label: "Quick", description: "2 searches" },
  { value: "standard", label: "Standard", description: "3–4 searches" },
  { value: "deep", label: "Deep", description: "5–6 searches" },
];

export function DepthToggle({ value, onChange, disabled }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[11px] tracking-widest uppercase dark:text-muted-foreground text-slate-500">
        Depth
      </span>
      <div className="flex items-center rounded-full dark:bg-white/5 bg-slate-100 p-0.5 gap-0.5">
        {MODES.map((m) => {
          const active = value === m.value;
          return (
            <button
              key={m.value}
              onClick={() => !disabled && onChange(m.value)}
              disabled={disabled}
              title={m.description}
              className={[
                "font-mono text-[11px] px-3 py-1 rounded-full transition-all duration-200 disabled:opacity-40 cursor-pointer",
                active
                  ? "bg-primary text-primary-foreground shadow-[0_0_10px_2px_rgb(59_130_246/0.35)]"
                  : "bg-transparent dark:text-muted-foreground text-slate-500 hover:dark:text-foreground hover:text-slate-700",
              ].join(" ")}
            >
              {m.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
