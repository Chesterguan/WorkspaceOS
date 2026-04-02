"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DraftCard } from "@/components/DraftCard";
import { DraftGeneratePanel } from "@/components/DraftGeneratePanel";
import { useProjectContext } from "@/components/ProjectContext";
import { useDrafts } from "@/lib/hooks/useDrafts";
import { Sparkles, FileText } from "lucide-react";
import type { Platform, DraftStatus } from "@/lib/types";
import { PLATFORM_LABELS } from "@/components/PlatformBadge";
import { cn } from "@/lib/utils";

const PLATFORMS: { value: Platform | "all"; label: string }[] = [
  { value: "all", label: "All platforms" },
  { value: "linkedin", label: PLATFORM_LABELS.linkedin },
  { value: "twitter", label: PLATFORM_LABELS.twitter },
  { value: "xiaohongshu", label: PLATFORM_LABELS.xiaohongshu },
  { value: "medium_outline", label: PLATFORM_LABELS.medium_outline },
  { value: "github_release", label: PLATFORM_LABELS.github_release },
];

const STATUSES: { value: DraftStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
  { value: "archived", label: "Archived" },
];

export default function DraftsPage() {
  const { project } = useProjectContext();
  const [platformFilter, setPlatformFilter] = useState<Platform | "all">("all");
  const [statusFilter, setStatusFilter] = useState<DraftStatus | "all">("all");
  const [generateOpen, setGenerateOpen] = useState(false);

  const { data, error, isLoading, mutate } = useDrafts(project.id, {
    platform: platformFilter === "all" ? undefined : platformFilter,
    status: statusFilter === "all" ? undefined : statusFilter,
  });

  const draftList = data ?? [];

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Drafts</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {draftList.length} draft{draftList.length !== 1 ? "s" : ""} across all platforms
          </p>
        </div>
        <Button onClick={() => setGenerateOpen(true)} className="gap-2">
          <Sparkles className="w-4 h-4" />
          Generate Draft
        </Button>
      </div>

      {/* Platform filter pills */}
      <div className="flex items-center gap-2 flex-wrap">
        {PLATFORMS.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => setPlatformFilter(p.value as Platform | "all")}
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium border transition-all",
              platformFilter === p.value
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Status tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        {STATUSES.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => setStatusFilter(s.value as DraftStatus | "all")}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-all -mb-px",
              statusFilter === s.value
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="animate-pulse space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-40 bg-secondary/40 rounded-lg" />
            ))}
          </div>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load drafts: {error.message}
        </div>
      ) : draftList.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
            <FileText className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">No drafts match your filters.</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setGenerateOpen(true)}
            className="gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Generate a draft
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {draftList.map((draft) => (
            <DraftCard
              key={draft.id}
              draft={draft}
              projectId={project.id}
              onFeedbackRecorded={() => mutate()}
              onDeleted={() => mutate()}
            />
          ))}
        </div>
      )}

      <DraftGeneratePanel
        projectId={project.id}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onGenerated={() => mutate()}
      />
    </div>
  );
}
