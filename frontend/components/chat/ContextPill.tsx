"use client";

import { cn } from "@/lib/utils";

interface ContextPillProps {
  label: string;
  active: boolean;
  onClick: () => void;
  activeClassName?: string;
}

export function ContextPill({ label, active, onClick, activeClassName }: ContextPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-3 py-1 rounded-full text-xs font-medium border transition-all select-none",
        active
          ? activeClassName || "bg-primary/15 text-primary border-primary/40"
          : "border-border text-muted-foreground hover:border-border/80 hover:text-foreground/70",
      )}
    >
      {label}
    </button>
  );
}
