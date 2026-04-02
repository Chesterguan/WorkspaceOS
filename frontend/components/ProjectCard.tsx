"use client";

import Link from "next/link";
import { formatDistanceToNow } from "@/lib/utils";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GitBranch, Clock, FileText, Circle } from "lucide-react";
import type { Project } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ProjectCardProps {
  project: Project;
  /**
   * ISO timestamp of the last completed sync run for this project.
   * If undefined, sync status indicator will show "never synced".
   */
  lastSyncAt?: string | null;
  /** Number of drafts associated with this project. */
  draftCount?: number;
}

/**
 * Returns the sync status tier based on how recently the project was synced.
 *   - "recent"  : synced within the last 7 days  — green dot
 *   - "stale"   : synced 7–30 days ago           — yellow dot
 *   - "never"   : never synced or >30 days ago   — grey dot
 */
function syncStatusTier(lastSyncAt?: string | null): "recent" | "stale" | "never" {
  if (!lastSyncAt) return "never";
  const diffMs = Date.now() - new Date(lastSyncAt).getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  if (diffDays <= 7) return "recent";
  if (diffDays <= 30) return "stale";
  return "never";
}

const SYNC_STATUS_STYLES = {
  recent: "text-emerald-500",
  stale: "text-amber-400",
  never: "text-muted-foreground/50",
} as const;

const SYNC_STATUS_LABELS = {
  recent: "Synced recently",
  stale: "Sync is stale",
  never: "Never synced",
} as const;

export function ProjectCard({ project, lastSyncAt, draftCount }: ProjectCardProps) {
  const tier = syncStatusTier(lastSyncAt);

  return (
    <Link href={`/projects/${project.id}/overview`}>
      <Card className="group hover:border-primary/50 hover:bg-card/80 transition-all duration-200 cursor-pointer h-full">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-base leading-tight group-hover:text-primary transition-colors">
                {project.name}
              </h3>
              {project.status === "demo" && (
                <Badge
                  className="text-[10px] px-1.5 py-0 bg-amber-500/15 text-amber-400 border-amber-500/30"
                  variant="outline"
                >
                  Demo
                </Badge>
              )}
            </div>
            {project.github_repo && (
              <Badge
                variant="outline"
                className="shrink-0 text-xs bg-secondary/50 font-mono"
              >
                <GitBranch className="w-3 h-3 mr-1" />
                {project.github_repo}
              </Badge>
            )}
          </div>
          {project.description && (
            <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
              {project.description}
            </p>
          )}
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {/* Last sync time with status indicator */}
            <span
              className="flex items-center gap-1.5"
              title={SYNC_STATUS_LABELS[tier]}
            >
              <Circle
                className={cn("w-2 h-2 fill-current", SYNC_STATUS_STYLES[tier])}
              />
              <Clock className="w-3.5 h-3.5" />
              {lastSyncAt
                ? `Synced ${formatDistanceToNow(lastSyncAt)}`
                : "Never synced"}
            </span>

            {/* Draft count badge */}
            {draftCount !== undefined && draftCount > 0 && (
              <span className="flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" />
                {draftCount} {draftCount === 1 ? "draft" : "drafts"}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
