"use client";

import { useRef, KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";

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
        className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 min-h-[56px]"
      />
      <Button
        onClick={submit}
        disabled={disabled}
        className="h-[56px] px-5 shrink-0"
      >
        Research
      </Button>
    </div>
  );
}
