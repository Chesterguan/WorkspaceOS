"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "@/lib/utils";
import { History, ChevronRight, X } from "lucide-react";
import type { BlogPostVersion } from "@/lib/types";

interface BlogVersionHistoryProps {
  versions: BlogPostVersion[];
  currentVersion?: number;
  onSelectVersion: (version: BlogPostVersion) => void;
  onClose: () => void;
}

export function BlogVersionHistory({
  versions,
  currentVersion,
  onSelectVersion,
  onClose,
}: BlogVersionHistoryProps) {
  const sorted = [...versions].sort((a, b) => b.version - a.version);

  return (
    // Slide-over panel
    <div className="flex flex-col h-full border-l border-border bg-card w-64 shrink-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          <History className="w-3.5 h-3.5" />
          Version History
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={onClose}
        >
          <X className="w-3.5 h-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sorted.length === 0 ? (
          <p className="text-xs text-muted-foreground px-2 py-4">
            No previous versions.
          </p>
        ) : (
          sorted.map((v) => {
            const isCurrent = v.version === currentVersion;
            return (
              <button
                key={v.id}
                type="button"
                onClick={() => !isCurrent && onSelectVersion(v)}
                disabled={isCurrent}
                className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-md text-left transition-colors ${
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
                <div className="flex-1 min-w-0">
                  <p className="text-xs truncate font-medium">{v.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDistanceToNow(v.saved_at)}
                  </p>
                </div>
                {isCurrent ? (
                  <span className="text-xs text-primary font-medium shrink-0">
                    Current
                  </span>
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                )}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
