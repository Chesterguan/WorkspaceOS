"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  AlertTriangle,
  Circle,
  Loader2,
  ChevronDown,
  ChevronRight,
  GitCompareArrows,
  Eye,
} from "lucide-react";
import type { PaperVersionInfo } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReviewTimelineProps {
  // Completed review passes returned from the API
  versions: PaperVersionInfo[];
  // Total expected passes — used to render pending placeholders
  totalPasses?: number;
  // Index of the currently-active pass during generation (0-based), or null when done
  activePassIndex?: number | null;
  // Currently selected version in the content area (1-based)
  selectedVersion: number;
  onSelectVersion: (version: number) => void;
  onCompareWithPrevious: (version: number) => void;
  className?: string;
}

// ─── Score helpers ─────────────────────────────────────────────────────────

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 8) return "text-green-400";
  if (score >= 6) return "text-yellow-400";
  return "text-red-400";
}

function scoreBadgeClass(score: number | null): string {
  if (score === null) return "border-border text-muted-foreground";
  if (score >= 8) return "bg-green-500/10 border-green-500/30 text-green-400";
  if (score >= 6) return "bg-yellow-500/10 border-yellow-500/30 text-yellow-400";
  return "bg-red-500/10 border-red-500/30 text-red-400";
}

// ─── Single pass entry ────────────────────────────────────────────────────────

interface PassEntryProps {
  pass: PaperVersionInfo;
  isSelected: boolean;
  isFirst: boolean;
  onSelect: () => void;
  onCompare: () => void;
}

function PassEntry({ pass, isSelected, isFirst, onSelect, onCompare }: PassEntryProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        isSelected
          ? "border-violet-500/40 bg-violet-500/5"
          : "border-border bg-card hover:border-border/80",
      )}
    >
      {/* Pass header */}
      <button
        type="button"
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Expand chevron */}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        )}

        {/* Pass info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium truncate">{pass.review_name}</span>
          </div>
          {pass.changes_made && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{pass.changes_made}</p>
          )}
        </div>

        {/* Score badge */}
        {pass.score !== null && (
          <Badge
            variant="outline"
            className={cn("text-xs shrink-0 tabular-nums", scoreBadgeClass(pass.score))}
          >
            {pass.score}/10
          </Badge>
        )}

        {/* Version badge */}
        <Badge
          variant="outline"
          className={cn(
            "text-xs shrink-0",
            isSelected
              ? "bg-violet-500/15 border-violet-500/40 text-violet-400"
              : "border-border text-muted-foreground",
          )}
        >
          v{pass.version}
        </Badge>
      </button>

      {/* Expandable review notes */}
      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-border/50 pt-2.5">
          {pass.review_notes && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                Review Notes
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {pass.review_notes}
              </p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-[11px] gap-1 border-violet-500/30 text-violet-400 hover:bg-violet-500/10"
              onClick={onSelect}
            >
              <Eye className="w-3 h-3" />
              View version
            </Button>
            {!isFirst && (
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-[11px] gap-1"
                onClick={onCompare}
              >
                <GitCompareArrows className="w-3 h-3" />
                Compare with previous
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Pending placeholder ──────────────────────────────────────────────────────

interface PendingPassProps {
  index: number;
  isActive: boolean;
  passNames: readonly string[];
}

function PendingPass({ index, isActive, passNames }: PendingPassProps) {
  const name = passNames[index] ?? `Pass ${index + 1}`;

  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2.5 flex items-center gap-3">
      {isActive ? (
        <Loader2 className="w-4 h-4 text-violet-400 animate-spin shrink-0" />
      ) : (
        <Circle className="w-4 h-4 text-muted-foreground/40 shrink-0" />
      )}
      <span className={cn("text-xs", isActive ? "text-foreground" : "text-muted-foreground/50")}>
        {name}
        {isActive && (
          <span className="ml-2 text-violet-400 animate-pulse">in progress…</span>
        )}
      </span>
    </div>
  );
}

// ─── Pass name catalogue ──────────────────────────────────────────────────────
// We know the backend runs 5 review passes; these labels map to the index.
const PASS_NAMES = [
  "Draft generation",
  "Technical review",
  "Clarity & structure",
  "Novelty & positioning",
  "Final polish",
] as const;

// ─── Timeline ────────────────────────────────────────────────────────────────

export function ReviewTimeline({
  versions,
  totalPasses = 5,
  activePassIndex = null,
  selectedVersion,
  onSelectVersion,
  onCompareWithPrevious,
  className,
}: ReviewTimelineProps) {
  const completedCount = versions.length;
  const pendingCount = totalPasses - completedCount;

  // Overall score across completed passes
  const scoresWithValues = versions.filter((v) => v.score !== null);
  const avgScore =
    scoresWithValues.length > 0
      ? scoresWithValues.reduce((s, v) => s + (v.score ?? 0), 0) / scoresWithValues.length
      : null;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Summary header */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          Review Pipeline
        </span>
        {avgScore !== null && (
          <span className={cn("text-xs font-semibold tabular-nums", scoreColor(avgScore))}>
            avg {avgScore.toFixed(1)}/10
          </span>
        )}
      </div>

      {/* Status legend */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground/60">
        <span className="flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3 text-green-400" /> Passed
        </span>
        <span className="flex items-center gap-1">
          <AlertTriangle className="w-3 h-3 text-yellow-400" /> Revised
        </span>
        <span className="flex items-center gap-1">
          <Loader2 className="w-3 h-3 text-violet-400" /> Active
        </span>
      </div>

      {/* Completed passes */}
      <div className="space-y-2">
        {versions.map((pass, idx) => (
          <div key={pass.version} className="flex items-start gap-2">
            {/* Status icon */}
            <div className="mt-2.5 shrink-0">
              {pass.score !== null && pass.score >= 8 ? (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              ) : pass.score !== null ? (
                <AlertTriangle className="w-4 h-4 text-yellow-400" />
              ) : (
                <Circle className="w-4 h-4 text-muted-foreground/40" />
              )}
            </div>

            {/* Entry card */}
            <div className="flex-1 min-w-0">
              <PassEntry
                pass={pass}
                isSelected={pass.version === selectedVersion}
                isFirst={idx === 0}
                onSelect={() => onSelectVersion(pass.version)}
                onCompare={() => onCompareWithPrevious(pass.version)}
              />
            </div>
          </div>
        ))}

        {/* Pending passes */}
        {Array.from({ length: pendingCount }).map((_, i) => {
          const passIndex = completedCount + i;
          const isActive = activePassIndex === passIndex;
          return (
            <div key={`pending-${passIndex}`} className="flex items-start gap-2">
              <div className="mt-2.5 shrink-0">
                {isActive ? (
                  <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />
                ) : (
                  <Circle className="w-4 h-4 text-muted-foreground/20" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <PendingPass
                  index={passIndex}
                  isActive={isActive}
                  passNames={PASS_NAMES}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
