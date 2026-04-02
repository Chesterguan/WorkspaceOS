"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ChevronDown,
  ChevronRight,
  GitCommit,
  Package,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
} from "lucide-react";
import { formatDate, formatDistanceToNow } from "@/lib/utils";
import type { SyncRun } from "@/lib/types";

const STATUS_CONFIG = {
  pending: {
    icon: Clock,
    color: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
    label: "Pending",
  },
  running: {
    icon: Loader2,
    color: "bg-blue-600/20 text-blue-400 border-blue-600/30",
    label: "Running",
  },
  completed: {
    icon: CheckCircle2,
    color: "bg-green-600/20 text-green-400 border-green-600/30",
    label: "Completed",
  },
  failed: {
    icon: AlertCircle,
    color: "bg-red-600/20 text-red-400 border-red-600/30",
    label: "Failed",
  },
};

interface SyncHistoryListProps {
  runs: SyncRun[];
}

export function SyncHistoryList({ runs }: SyncHistoryListProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (runs.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <RefreshCw className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <p className="text-sm">No sync runs yet. Click "Sync Now" to get started.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {runs.map((run) => {
        const config = STATUS_CONFIG[run.status];
        const StatusIcon = config.icon;
        const isExpanded = expandedIds.has(run.id);

        return (
          <div
            key={run.id}
            className="border border-border rounded-lg overflow-hidden bg-card"
          >
            <button
              type="button"
              className="w-full flex items-center gap-3 p-4 text-left hover:bg-secondary/30 transition-colors"
              onClick={() => toggleExpand(run.id)}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
              )}

              <Badge
                variant="outline"
                className={`text-xs shrink-0 ${config.color}`}
              >
                <StatusIcon
                  className={`w-3 h-3 mr-1 ${run.status === "running" ? "animate-spin" : ""}`}
                />
                {config.label}
              </Badge>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">
                  {formatDate(run.triggered_at)}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {formatDistanceToNow(run.triggered_at)}
                </p>
              </div>

              <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
                <span className="flex items-center gap-1">
                  <GitCommit className="w-3.5 h-3.5" />
                  {run.commits_fetched} commits
                </span>
                <span className="flex items-center gap-1">
                  <Package className="w-3.5 h-3.5" />
                  {run.releases_fetched} releases
                </span>
              </div>
            </button>

            {isExpanded && (
              <div className="border-t border-border px-4 pb-4 pt-3 space-y-4">
                {run.error_message && (
                  <div className="flex items-start gap-2 text-sm text-red-400 bg-red-950/30 rounded-md p-3">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{run.error_message}</span>
                  </div>
                )}

                {run.evolution_summary && (
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Evolution Summary
                    </p>
                    <p className="text-sm text-foreground/80 leading-relaxed">
                      {run.evolution_summary}
                    </p>
                  </div>
                )}

                {run.commits_fetched > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Commits fetched: {run.commits_fetched}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Needed for the empty state icon
function RefreshCw({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  );
}
