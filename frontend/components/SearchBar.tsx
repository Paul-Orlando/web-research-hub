"use client";

import { useRef, KeyboardEvent } from "react";

interface Props {
  onSearch: (query: string) => void;
  disabled?: boolean;
}

export function SearchBar({ onSearch, disabled }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const q = ref.current?.value.trim();
    if (!q || disabled) return;
    onSearch(q);
    if (ref.current) ref.current.value = "";
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex gap-2 items-end w-full">
      <textarea
        ref={ref}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder="What would you like to research today?"
        rows={2}
        className="flex-1 resize-none rounded-lg border dark:border-white/8 border-slate-200 dark:bg-[#0d1428] bg-white px-4 py-3 text-sm dark:text-white text-slate-800 shadow-sm placeholder:dark:text-white/25 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60 dark:focus-visible:ring-cyan-400/60 disabled:opacity-50 min-h-[64px] transition-shadow duration-200"
      />
      <button
        onClick={submit}
        disabled={disabled}
        className="h-[64px] px-6 shrink-0 rounded-lg bg-blue-500 hover:bg-blue-400 text-white font-mono text-sm tracking-wide shadow-md hover:shadow-[0_0_18px_4px_rgb(59_130_246/0.4)] transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
      >
        Research
      </button>
    </div>
  );
}
