"use client";

import { SyncTriggerButton } from "@/components/SyncTriggerButton";
import { SyncHistoryList } from "@/components/SyncHistoryList";
import { useProjectContext } from "@/components/ProjectContext";
import { useSyncRuns } from "@/lib/hooks/useSyncRuns";
import { RefreshCw } from "lucide-react";

export default function SyncPage() {
  const { project } = useProjectContext();
  const { data: syncRuns, error, isLoading, mutate } = useSyncRuns(project.id);

  return (
    <div className="p-8 space-y-6 max-w-4xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Sync Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Fetch the latest commits and releases from GitHub, then generate an evolution summary.
          </p>
        </div>
        <SyncTriggerButton
          projectId={project.id}
          onSyncStarted={() => mutate()}
        />
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-secondary/40 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load sync history: {error.message}
        </div>
      ) : (
        <SyncHistoryList runs={syncRuns ?? []} />
      )}
    </div>
  );
}
