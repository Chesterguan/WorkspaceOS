"use client";

import { Badge } from "@/components/ui/badge";
import { formatDistanceToNow } from "@/lib/utils";
import { Link2, Tag, Layers, Sparkles, GitCommitHorizontal, BookOpen, Rocket } from "lucide-react";
import type { MemoryEntry, MemoryEntryType } from "@/lib/types";

const TYPE_COLORS: Record<MemoryEntryType, string> = {
  milestone: "bg-purple-600/20 text-purple-400 border-purple-600/30",
  insight: "bg-blue-600/20 text-blue-400 border-blue-600/30",
  feedback: "bg-orange-600/20 text-orange-400 border-orange-600/30",
  decision: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  note: "bg-zinc-600/20 text-zinc-400 border-zinc-600/30",
  // AI-generated types
  theme_extraction: "bg-blue-600/20 text-blue-400 border-blue-600/30",
  consolidated_summary: "bg-purple-600/20 text-purple-400 border-purple-600/30",
  preference_pattern: "bg-amber-600/20 text-amber-400 border-amber-600/30",
  // Sync-generated types
  commit_summary: "bg-green-600/20 text-green-400 border-green-600/30",
  readme_content: "bg-teal-600/20 text-teal-400 border-teal-600/30",
  release_note: "bg-cyan-600/20 text-cyan-400 border-cyan-600/30",
  user_annotation: "bg-zinc-600/20 text-zinc-400 border-zinc-600/30",
  wiki_summary: "bg-indigo-600/20 text-indigo-400 border-indigo-600/30",
};

// Row background tint for AI/sync-generated types to make them visually distinct
const TYPE_ROW_BG: Partial<Record<MemoryEntryType, string>> = {
  theme_extraction: "bg-blue-950/20 border-blue-900/30",
  consolidated_summary: "bg-purple-950/20 border-purple-900/30",
  preference_pattern: "bg-amber-950/20 border-amber-900/30",
  commit_summary: "bg-green-950/20 border-green-900/30",
  readme_content: "bg-teal-950/20 border-teal-900/30",
  release_note: "bg-cyan-950/20 border-cyan-900/30",
};

// Lucide icons for AI/sync-generated entry types
const TYPE_ICONS: Partial<Record<MemoryEntryType, React.ElementType>> = {
  theme_extraction: Tag,
  consolidated_summary: Layers,
  preference_pattern: Sparkles,
  commit_summary: GitCommitHorizontal,
  readme_content: BookOpen,
  release_note: Rocket,
};

// Human-readable labels for all types
const TYPE_LABELS: Record<MemoryEntryType, string> = {
  milestone: "Milestone",
  insight: "Insight",
  feedback: "Feedback",
  decision: "Decision",
  note: "Note",
  theme_extraction: "Theme Extraction",
  consolidated_summary: "Summary",
  preference_pattern: "Preference",
  commit_summary: "Commit Summary",
  readme_content: "README",
  release_note: "Release Note",
  user_annotation: "Annotation",
  wiki_summary: "Wiki Summary",
};

interface MemoryLogListProps {
  entries: MemoryEntry[];
}

export function MemoryLogList({ entries }: MemoryLogListProps) {
  if (entries.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p className="text-sm">No memory entries found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {entries.map((entry) => {
        const TypeIcon = TYPE_ICONS[entry.entry_type];
        const rowBg = TYPE_ROW_BG[entry.entry_type] ?? "";

        return (
          <div
            key={entry.id}
            className={`flex gap-4 p-4 rounded-lg border transition-colors ${
              rowBg
                ? rowBg
                : "border-border bg-card hover:border-border/80"
            }`}
          >
            {/* Type icon for AI/sync-generated entries */}
            {TypeIcon && (
              <div className="pt-0.5 shrink-0 self-start">
                <div
                  className={`w-7 h-7 rounded-md flex items-center justify-center ${
                    TYPE_COLORS[entry.entry_type]?.split(" ")[0] ?? "bg-zinc-600/20"
                  }`}
                >
                  <TypeIcon
                    className={`w-3.5 h-3.5 ${
                      TYPE_COLORS[entry.entry_type]?.split(" ")[1] ?? "text-zinc-400"
                    }`}
                  />
                </div>
              </div>
            )}

            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge
                  variant="outline"
                  className={`text-xs ${TYPE_COLORS[entry.entry_type] ?? "bg-zinc-600/20 text-zinc-400 border-zinc-600/30"}`}
                >
                  {TYPE_LABELS[entry.entry_type] ?? entry.entry_type}
                </Badge>
                {/* Auto-generated indicator for sync/AI types */}
                {TypeIcon && (
                  <span className="text-xs text-muted-foreground bg-secondary/40 px-1.5 py-0.5 rounded-sm">
                    {(["commit_summary", "readme_content", "release_note"] as MemoryEntryType[]).includes(entry.entry_type)
                      ? "from sync"
                      : "AI generated"}
                  </span>
                )}
              </div>

              <p className="text-sm text-foreground/85 leading-relaxed line-clamp-3">
                {entry.content}
              </p>

              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                {entry.source_ref && (
                  <span className="flex items-center gap-1 truncate max-w-xs">
                    <Link2 className="w-3 h-3 shrink-0" />
                    <span className="truncate">{entry.source_ref}</span>
                  </span>
                )}
                <span className="ml-auto shrink-0">
                  {formatDistanceToNow(entry.created_at)}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
