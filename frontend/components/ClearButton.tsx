"use client";

interface Props {
  onClick: () => void;
  disabled?: boolean;
}

export function ClearButton({ onClick, disabled }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="h-9 px-4 shrink-0 rounded-lg border border-transparent font-mono text-xs text-muted-foreground hover:text-red-400 hover:bg-red-500/10 hover:border-red-500/20 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
    >
      Clear
    </button>
  );
}
