"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { workspace as workspaceApi } from "@/lib/api";
import { formatDistanceToNow } from "@/lib/utils";
import { GitBranch, GitCommitHorizontal, RefreshCw, Loader2, HardDrive } from "lucide-react";
import { toast } from "sonner";
import type { WorkspaceContext, WorkspaceSnapshot } from "@/lib/types";

interface WorkspaceStatusProps {
  projectId: string;
  context: WorkspaceContext | null;
  onScanned: (snapshot: WorkspaceSnapshot) => void;
  lastScannedAt: string | null;
}

// Count lines in git_status that represent actual changed files (non-empty, non-header)
function countUncommittedFiles(gitStatus: string | null): number {
  if (!gitStatus) return 0;
  return gitStatus
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .length;
}

export function WorkspaceStatus({
  projectId,
  context,
  onScanned,
  lastScannedAt,
}: WorkspaceStatusProps) {
  const [isScanning, setIsScanning] = useState(false);

  async function handleScan() {
    setIsScanning(true);
    try {
      const snapshot = await workspaceApi.scan(projectId);
      onScanned(snapshot);
      toast.success("Workspace scanned");
    } catch (err) {
      toast.error("Scan failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsScanning(false);
    }
  }

  const uncommittedCount = countUncommittedFiles(context?.git_status ?? null);

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-secondary/20 text-xs">
      <HardDrive className="w-3 h-3 text-muted-foreground shrink-0" />

      {context?.has_snapshot ? (
        <>
          {/* Git branch badge */}
          {context.git_branch && (
            <Badge
              variant="outline"
              className="text-xs py-0 h-5 font-mono bg-green-600/10 text-green-400 border-green-600/30 gap-1"
            >
              <GitBranch className="w-2.5 h-2.5" />
              {context.git_branch}
            </Badge>
          )}

          {/* Uncommitted changes */}
          {uncommittedCount > 0 && (
            <Badge
              variant="outline"
              className="text-xs py-0 h-5 bg-yellow-600/10 text-yellow-400 border-yellow-600/30 gap-1"
            >
              <GitCommitHorizontal className="w-2.5 h-2.5" />
              {uncommittedCount} uncommitted
            </Badge>
          )}

          {/* Last scan time */}
          {lastScannedAt && (
            <span className="text-muted-foreground ml-1">
              scanned {formatDistanceToNow(lastScannedAt)}
            </span>
          )}
        </>
      ) : (
        <span className="text-muted-foreground">No workspace scan yet</span>
      )}

      {/* Scan button — always visible on the right */}
      <Button
        variant="outline"
        size="sm"
        className="ml-auto h-6 text-xs px-2 gap-1"
        onClick={handleScan}
        disabled={isScanning}
      >
        {isScanning ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <RefreshCw className="w-3 h-3" />
        )}
        Scan Now
      </Button>
    </div>
  );
}
