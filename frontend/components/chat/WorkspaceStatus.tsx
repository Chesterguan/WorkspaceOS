"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { github as githubApi, workspace as workspaceApi, type GitHubBranch } from "@/lib/api";
import { formatDistanceToNow } from "@/lib/utils";
import {
  GitBranch,
  GitCommitHorizontal,
  RefreshCw,
  Loader2,
  HardDrive,
  ChevronDown,
} from "lucide-react";
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
  // Branch the next scan should target. `undefined` = use the project's
  // default (backend falls back to project.github_branch). Only meaningful
  // for remote-only projects that hit the repo_cache clone path.
  const [selectedBranch, setSelectedBranch] = useState<string | undefined>(undefined);
  const [branches, setBranches] = useState<GitHubBranch[] | null>(null);
  const [branchesLoading, setBranchesLoading] = useState(false);

  async function loadBranches() {
    if (branches !== null || branchesLoading) return;
    setBranchesLoading(true);
    try {
      const list = await githubApi.listBranches(projectId);
      setBranches(list);
    } catch {
      // Silent failure — projects without a github_repo just won't have
      // a branch list, and the user can still scan whatever local_path exists.
      setBranches([]);
    } finally {
      setBranchesLoading(false);
    }
  }

  async function handleScan() {
    setIsScanning(true);
    try {
      const snapshot = await workspaceApi.scan(projectId, { branch: selectedBranch });
      onScanned(snapshot);
      toast.success(
        selectedBranch
          ? `Scanned branch "${selectedBranch}"`
          : "Workspace scanned",
      );
    } catch (err) {
      toast.error("Scan failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsScanning(false);
    }
  }

  const uncommittedCount = countUncommittedFiles(context?.git_status ?? null);
  const defaultBranch = branches?.find((b) => b.is_default)?.name;
  // Label shown on the branch picker: user's choice > scanned branch >
  // repo default > generic fallback.
  const pickerLabel =
    selectedBranch ?? context?.git_branch ?? defaultBranch ?? "branch";

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

      {/* Branch picker + Scan button — right-aligned group */}
      <div className="ml-auto flex items-center gap-1.5">
        <DropdownMenu onOpenChange={(open) => open && loadBranches()}>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                className="inline-flex items-center gap-1 h-6 px-2 text-xs rounded-md border border-border bg-background/60 hover:bg-secondary/60 transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 max-w-[160px]"
                disabled={isScanning}
                title="Choose branch to scan"
              />
            }
          >
            <GitBranch className="w-3 h-3 text-muted-foreground shrink-0" />
            <span className="truncate">{pickerLabel}</span>
            <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-64 overflow-y-auto">
            {branchesLoading && (
              <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground">
                <Loader2 className="w-3 h-3 animate-spin" />
                Loading branches…
              </div>
            )}
            {!branchesLoading && branches && branches.length === 0 && (
              <div className="px-2 py-1.5 text-xs text-muted-foreground">
                No remote branches
              </div>
            )}
            {!branchesLoading && branches && branches.length > 0 && (
              <>
                <DropdownMenuItem
                  onClick={() => setSelectedBranch(undefined)}
                  className={!selectedBranch ? "text-primary" : ""}
                >
                  <span className="text-[10px] text-muted-foreground mr-2">auto</span>
                  project default
                </DropdownMenuItem>
                {branches.map((b) => (
                  <DropdownMenuItem
                    key={b.name}
                    onClick={() => setSelectedBranch(b.name)}
                    className={selectedBranch === b.name ? "text-primary" : ""}
                  >
                    <GitBranch className="w-3 h-3 mr-1.5 text-muted-foreground" />
                    <span className="truncate">{b.name}</span>
                    {b.is_default && (
                      <Badge
                        variant="outline"
                        className="ml-auto text-[9px] px-1 py-0 h-4"
                      >
                        default
                      </Badge>
                    )}
                  </DropdownMenuItem>
                ))}
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          variant="outline"
          size="sm"
          className="h-6 text-xs px-2 gap-1"
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
    </div>
  );
}
