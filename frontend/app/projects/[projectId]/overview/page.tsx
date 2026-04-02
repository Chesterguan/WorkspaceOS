"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { EvolutionSummaryCard } from "@/components/EvolutionSummaryCard";
import { SyncTriggerButton } from "@/components/SyncTriggerButton";
import { DraftGeneratePanel } from "@/components/DraftGeneratePanel";
import { useProjectContext } from "@/components/ProjectContext";
import { useSyncRuns } from "@/lib/hooks/useSyncRuns";
import { useDrafts } from "@/lib/hooks/useDrafts";
import { useMemory } from "@/lib/hooks/useMemory";
import { formatDistanceToNow } from "@/lib/utils";
import {
  FileText,
  RefreshCw,
  Clock,
  Brain,
  Sparkles,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import { PlatformBadge } from "@/components/PlatformBadge";

export default function OverviewPage() {
  const { project } = useProjectContext();
  const { data: syncRuns, mutate: mutateSyncs } = useSyncRuns(project.id);
  const { data: draftsData, mutate: mutateDrafts } = useDrafts(project.id);
  const { data: memoryEntries } = useMemory(project.id);
  const [generateOpen, setGenerateOpen] = useState(false);

  const latestSync = syncRuns?.[0];
  const recentDrafts = (draftsData ?? []).slice(0, 5);
  const totalSyncs = syncRuns?.length ?? 0;
  const totalDrafts = draftsData?.length ?? 0;
  const memoryCount = memoryEntries?.length ?? 0;

  return (
    <div className="p-8 space-y-8 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          {project.description && (
            <p className="text-sm text-muted-foreground mt-1">
              {project.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Link href={`/projects/${project.id}/chat`}>
            <Button variant="outline" className="gap-2">
              <MessageSquare className="w-4 h-4" />
              Chat
            </Button>
          </Link>
          <SyncTriggerButton
            projectId={project.id}
            onSyncStarted={() => mutateSyncs()}
            variant="outline"
          />
          <Button
            className="gap-2"
            onClick={() => setGenerateOpen(true)}
          >
            <Sparkles className="w-4 h-4" />
            Generate Draft
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" />
              Total Drafts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">{totalDrafts}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" />
              Total Syncs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">{totalSyncs}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              Last Sync
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {latestSync
                ? formatDistanceToNow(latestSync.triggered_at)
                : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
              <Brain className="w-3.5 h-3.5" />
              Memory Entries
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">{memoryCount}</p>
          </CardContent>
        </Card>
      </div>

      {/* Evolution summary */}
      {latestSync?.evolution_summary && (
        <EvolutionSummaryCard summary={latestSync.evolution_summary} />
      )}

      <Separator />

      {/* Recent drafts */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Recent Drafts</h2>
          <Link href={`/projects/${project.id}/drafts`}>
            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground">
              View all
            </Button>
          </Link>
        </div>

        {recentDrafts.length === 0 ? (
          <div className="text-center py-8 text-sm text-muted-foreground border border-dashed border-border rounded-lg">
            No drafts yet.{" "}
            <button
              type="button"
              onClick={() => setGenerateOpen(true)}
              className="text-primary hover:underline"
            >
              Generate your first draft
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            {recentDrafts.map((draft, i) => (
              <Link
                key={draft.id}
                href={`/projects/${project.id}/drafts/${draft.id}`}
                className={`flex items-center gap-3 px-4 py-3 hover:bg-secondary/30 transition-colors ${i > 0 ? "border-t border-border" : ""}`}
              >
                <PlatformBadge platform={draft.platform} />
                <p className="flex-1 text-sm text-foreground/80 truncate">{draft.content}</p>
                <span className="text-xs text-muted-foreground shrink-0">
                  {formatDistanceToNow(draft.updated_at)}
                </span>
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
              </Link>
            ))}
          </div>
        )}
      </div>

      <DraftGeneratePanel
        projectId={project.id}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onGenerated={() => mutateDrafts()}
      />
    </div>
  );
}
