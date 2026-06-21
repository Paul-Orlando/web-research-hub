"use client";

import { Button } from "@/components/ui/button";
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
    <div className="flex items-center gap-1.5">
      <span className="text-sm text-muted-foreground mr-1">Depth:</span>
      {MODES.map((m) => (
        <Button
          key={m.value}
          size="sm"
          variant={value === m.value ? "default" : "outline"}
          onClick={() => onChange(m.value)}
          disabled={disabled}
          className="text-xs h-7 px-3"
          title={m.description}
        >
          {m.label}
        </Button>
      ))}
    </div>
  );
}
