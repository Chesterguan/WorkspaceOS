"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { github } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Search,
  Star,
  GitBranch,
  GitFork,
  Loader2,
  Clock,
} from "lucide-react";
import { formatDistanceToNow } from "@/lib/utils";
import type { GitHubRepo } from "@/lib/types";

// Skeleton row for loading state
function RepoRowSkeleton() {
  return (
    <div className="flex items-start gap-3 px-4 py-3 border-b border-border last:border-0 animate-pulse">
      <div className="mt-0.5 w-4 h-4 rounded bg-secondary shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3.5 w-40 bg-secondary rounded" />
        <div className="h-3 w-64 bg-secondary/60 rounded" />
        <div className="flex gap-2">
          <div className="h-4 w-14 bg-secondary/60 rounded-full" />
          <div className="h-4 w-10 bg-secondary/60 rounded-full" />
        </div>
      </div>
    </div>
  );
}

const LANGUAGE_COLORS: Record<string, string> = {
  TypeScript: "bg-blue-600/20 text-blue-400 border-blue-600/30",
  JavaScript: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  Python: "bg-green-600/20 text-green-400 border-green-600/30",
  Go: "bg-sky-600/20 text-sky-400 border-sky-600/30",
  Rust: "bg-orange-600/20 text-orange-400 border-orange-600/30",
  Java: "bg-red-600/20 text-red-400 border-red-600/30",
  "C++": "bg-pink-600/20 text-pink-400 border-pink-600/30",
  Ruby: "bg-rose-600/20 text-rose-400 border-rose-600/30",
  Swift: "bg-orange-600/20 text-orange-300 border-orange-600/30",
  Kotlin: "bg-purple-600/20 text-purple-400 border-purple-600/30",
};

function languageBadgeClass(lang: string | null): string {
  if (!lang) return "bg-zinc-600/20 text-zinc-400 border-zinc-600/30";
  return (
    LANGUAGE_COLORS[lang] ?? "bg-zinc-600/20 text-zinc-400 border-zinc-600/30"
  );
}

export function GitHubRepoSelector() {
  const router = useRouter();
  const { data: repos, error, isLoading } = useSWR<GitHubRepo[]>(
    "/github/repos",
    () => github.listRepos(),
  );

  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isImporting, setIsImporting] = useState(false);

  const filtered = useMemo(() => {
    if (!repos) return [];
    const q = search.toLowerCase().trim();
    if (!q) return repos;
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q),
    );
  }, [repos, search]);

  function toggleRepo(fullName: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(fullName)) {
        next.delete(fullName);
      } else {
        next.add(fullName);
      }
      return next;
    });
  }

  function toggleAll() {
    if (!filtered) return;
    const allKeys = filtered.map((r) => r.full_name);
    const allSelected = allKeys.every((k) => selected.has(k));
    if (allSelected) {
      setSelected((prev) => {
        const next = new Set(prev);
        allKeys.forEach((k) => next.delete(k));
        return next;
      });
    } else {
      setSelected((prev) => {
        const next = new Set(prev);
        allKeys.forEach((k) => next.add(k));
        return next;
      });
    }
  }

  async function handleImport() {
    if (!repos) return;
    const toImport = repos.filter((r) => selected.has(r.full_name));
    if (toImport.length === 0) return;

    setIsImporting(true);
    try {
      const result = await github.importRepos({
        repos: toImport.map((r) => ({
          full_name: r.full_name,
          default_branch: r.default_branch,
        })),
      });

      const importedCount = result.created.length;
      const skippedCount = result.skipped.length;
      toast.success(`Imported ${importedCount} project${importedCount !== 1 ? "s" : ""}`, {
        description:
          skippedCount > 0
            ? `${skippedCount} repo${skippedCount !== 1 ? "s" : ""} already existed and were skipped.`
            : undefined,
      });
      router.push("/projects");
    } catch (err) {
      toast.error("Import failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsImporting(false);
    }
  }

  const selectedCount = selected.size;
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((r) => selected.has(r.full_name));

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search repositories..."
          className="pl-9 bg-secondary/40"
        />
      </div>

      {/* Repo list */}
      <div className="rounded-lg border border-border overflow-hidden bg-card">
        {/* Header row with select-all */}
        {!isLoading && !error && filtered.length > 0 && (
          <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-secondary/20">
            <input
              type="checkbox"
              checked={allFilteredSelected}
              onChange={toggleAll}
              className="w-4 h-4 rounded accent-primary cursor-pointer"
              aria-label="Select all"
            />
            <span className="text-xs text-muted-foreground">
              {filtered.length} repositor{filtered.length !== 1 ? "ies" : "y"}
              {search && " matching search"}
            </span>
          </div>
        )}

        {/* Loading skeletons */}
        {isLoading && (
          <div>
            {Array.from({ length: 6 }).map((_, i) => (
              <RepoRowSkeleton key={i} />
            ))}
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-destructive">
              Failed to load repositories: {error.message}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Make sure your GitHub token is configured.
            </p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
            <GitFork className="w-10 h-10 opacity-30" />
            <p className="text-sm">
              {search ? "No repositories match your search." : "No repositories found."}
            </p>
          </div>
        )}

        {/* Repo rows */}
        {!isLoading && !error && (
          <div className="max-h-[400px] overflow-y-auto">
            {filtered.map((repo) => {
              const isChecked = selected.has(repo.full_name);
              return (
                <label
                  key={repo.full_name}
                  className={`flex items-start gap-3 px-4 py-3 border-b border-border last:border-0 cursor-pointer transition-colors hover:bg-secondary/20 ${
                    isChecked ? "bg-primary/5" : ""
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleRepo(repo.full_name)}
                    className="mt-0.5 w-4 h-4 rounded accent-primary cursor-pointer shrink-0"
                  />
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground truncate">
                        {repo.full_name}
                      </span>
                    </div>
                    {repo.description && (
                      <p className="text-xs text-muted-foreground line-clamp-1">
                        {repo.description}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      {repo.language && (
                        <Badge
                          variant="outline"
                          className={`text-xs px-1.5 py-0 ${languageBadgeClass(repo.language)}`}
                        >
                          {repo.language}
                        </Badge>
                      )}
                      <span className="flex items-center gap-1">
                        <Star className="w-3 h-3" />
                        {repo.stargazers_count.toLocaleString()}
                      </span>
                      <span className="flex items-center gap-1">
                        <GitBranch className="w-3 h-3" />
                        {repo.default_branch}
                      </span>
                      <span className="flex items-center gap-1 ml-auto">
                        <Clock className="w-3 h-3" />
                        {formatDistanceToNow(repo.updated_at)}
                      </span>
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* Import button */}
      <Button
        onClick={handleImport}
        disabled={selectedCount === 0 || isImporting}
        className="w-full gap-2"
      >
        {isImporting ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <GitFork className="w-4 h-4" />
        )}
        {isImporting
          ? "Importing..."
          : selectedCount > 0
          ? `Import Selected (${selectedCount})`
          : "Import Selected"}
      </Button>
    </div>
  );
}
