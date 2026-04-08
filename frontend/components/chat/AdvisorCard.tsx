"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";
import type { AdvisorInfo } from "@/lib/advisors";

interface AdvisorCardProps {
  advisor: AdvisorInfo;
  size: "sm" | "lg";
  selected?: boolean;
  onClick?: () => void;
}

export function AdvisorCard({ advisor, size, selected, onClick }: AdvisorCardProps) {
  if (size === "sm") {
    return (
      <div className="flex items-center gap-2">
        <div
          className="shrink-0 rounded-full overflow-hidden border-2"
          style={{ borderColor: advisor.color }}
        >
          <Image src={advisor.avatar} alt={advisor.name} width={28} height={28} className="rounded-full" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color: advisor.color }}>{advisor.name}</p>
          <p className="text-[10px] text-muted-foreground truncate">{advisor.tagline}</p>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center gap-1.5 px-3 py-2.5 rounded-lg border transition-all text-center shrink-0",
        "hover:bg-secondary/50",
        selected ? "border-2 bg-secondary/30" : "border-border",
      )}
      style={selected ? { borderColor: advisor.color } : undefined}
    >
      <div className="rounded-full overflow-hidden border-2" style={{ borderColor: advisor.color }}>
        <Image src={advisor.avatar} alt={advisor.name} width={48} height={48} className="rounded-full" />
      </div>
      <p className="text-xs font-semibold truncate max-w-[80px]">{advisor.name}</p>
      <p className="text-[9px] text-muted-foreground truncate max-w-[80px]">{advisor.tagline}</p>
    </button>
  );
}
