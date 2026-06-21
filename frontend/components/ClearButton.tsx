"use client";

import { Button } from "@/components/ui/button";

interface Props {
  onClick: () => void;
  disabled?: boolean;
}

export function ClearButton({ onClick, disabled }: Props) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onClick}
      disabled={disabled}
      className="h-9 px-4 text-sm text-muted-foreground hover:text-foreground shrink-0"
    >
      Clear
    </Button>
  );
}
