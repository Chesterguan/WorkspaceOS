"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import type { DiffLine } from "@/lib/types";

// ─── LCS-based line diff ───────────────────────────────────────────────────
// Computes a longest-common-subsequence diff between two arrays of lines.
// Returns a flat list of DiffLine entries in document order.

function lcs(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  // Build dp table
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp;
}

export function computeDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");

  const dp = lcs(oldLines, newLines);
  const result: DiffLine[] = [];

  // Traceback through dp to reconstruct the diff
  let i = oldLines.length;
  let j = newLines.length;
  const ops: DiffLine[] = [];

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      ops.push({ type: "same", content: oldLines[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ type: "add", content: newLines[j - 1] });
      j--;
    } else {
      ops.push({ type: "remove", content: oldLines[i - 1] });
      i--;
    }
  }

  // ops is built in reverse order
  ops.reverse();
  result.push(...ops);
  return result;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface PaperDiffViewProps {
  oldText: string;
  newText: string;
  oldLabel?: string;
  newLabel?: string;
  className?: string;
}

export function PaperDiffView({
  oldText,
  newText,
  oldLabel = "Previous version",
  newLabel = "Current version",
  className,
}: PaperDiffViewProps) {
  const lines = useMemo(() => computeDiff(oldText, newText), [oldText, newText]);

  // Assign side-by-side line numbers
  let oldLineNum = 0;
  let newLineNum = 0;

  const annotated = lines.map((line) => {
    let leftNum: number | null = null;
    let rightNum: number | null = null;

    if (line.type === "remove") {
      oldLineNum++;
      leftNum = oldLineNum;
    } else if (line.type === "add") {
      newLineNum++;
      rightNum = newLineNum;
    } else {
      oldLineNum++;
      newLineNum++;
      leftNum = oldLineNum;
      rightNum = newLineNum;
    }

    return { ...line, leftNum, rightNum };
  });

  const addCount = lines.filter((l) => l.type === "add").length;
  const removeCount = lines.filter((l) => l.type === "remove").length;

  return (
    <div className={cn("flex flex-col min-h-0", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Diff view</span>
          <span className="text-green-400">+{addCount} added</span>
          <span className="text-red-400">-{removeCount} removed</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="px-2 py-0.5 rounded bg-red-500/10 border border-red-500/20 text-red-400">
            {oldLabel}
          </span>
          <span className="px-2 py-0.5 rounded bg-green-500/10 border border-green-500/20 text-green-400">
            {newLabel}
          </span>
        </div>
      </div>

      {/* Diff lines */}
      <div className="flex-1 overflow-y-auto font-mono text-xs leading-5">
        {annotated.map((line, idx) => (
          <div
            key={idx}
            className={cn(
              "flex items-start gap-0 group",
              line.type === "remove" && "bg-red-500/10",
              line.type === "add" && "bg-green-500/10",
            )}
          >
            {/* Left line number (old) */}
            <span
              className={cn(
                "select-none w-10 shrink-0 text-right pr-2 py-0.5 border-r border-border/50",
                "text-muted-foreground/50",
                line.type === "remove" && "text-red-400/60",
              )}
            >
              {line.leftNum ?? ""}
            </span>

            {/* Right line number (new) */}
            <span
              className={cn(
                "select-none w-10 shrink-0 text-right pr-2 py-0.5 border-r border-border/50 mr-2",
                "text-muted-foreground/50",
                line.type === "add" && "text-green-400/60",
              )}
            >
              {line.rightNum ?? ""}
            </span>

            {/* Change gutter symbol */}
            <span
              className={cn(
                "select-none w-4 shrink-0 py-0.5 font-bold",
                line.type === "remove" && "text-red-400",
                line.type === "add" && "text-green-400",
                line.type === "same" && "text-muted-foreground/30",
              )}
            >
              {line.type === "remove" ? "−" : line.type === "add" ? "+" : " "}
            </span>

            {/* Line content */}
            <span
              className={cn(
                "flex-1 py-0.5 whitespace-pre-wrap break-all",
                line.type === "remove" && "text-red-300 line-through decoration-red-500/50",
                line.type === "add" && "text-green-300",
                line.type === "same" && "text-muted-foreground",
              )}
            >
              {line.content || " "}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
