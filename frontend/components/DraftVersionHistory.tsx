"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "@/lib/utils";
import { History, ChevronRight } from "lucide-react";
import type { Draft } from "@/lib/types";

interface DraftVersionHistoryProps {
  versions: Draft[];
  currentVersion: number;
  onSelectVersion: (draft: Draft) => void;
}

export function DraftVersionHistory({
  versions,
  currentVersion,
  onSelectVersion,
}: DraftVersionHistoryProps) {
  const sorted = [...versions].sort((a, b) => b.version - a.version);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide pb-1">
        <History className="w-3.5 h-3.5" />
        Version History
      </div>
      {sorted.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">No previous versions.</p>
      ) : (
        <div className="space-y-1">
          {sorted.map((v) => {
            const isCurrent = v.version === currentVersion;
            return (
              <button
                key={v.id}
                type="button"
                onClick={() => !isCurrent && onSelectVersion(v)}
                disabled={isCurrent}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-left text-sm transition-colors ${
                  isCurrent
                    ? "bg-primary/15 cursor-default"
                    : "hover:bg-secondary/50 cursor-pointer"
                }`}
              >
                <Badge
                  variant="outline"
                  className={`text-xs shrink-0 ${isCurrent ? "border-primary/50 text-primary" : ""}`}
                >
                  v{v.version}
                </Badge>
                <span className="flex-1 text-xs text-muted-foreground">
                  {formatDistanceToNow(v.updated_at)}
                </span>
                {isCurrent && (
                  <span className="text-xs text-primary font-medium">Current</span>
                )}
                {!isCurrent && (
                  <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
