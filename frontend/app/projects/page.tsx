"use client";

import Link from "next/link";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ProjectCard } from "@/components/ProjectCard";
import { useProjects } from "@/lib/hooks/useProjects";
import { useProjectStats } from "@/lib/hooks/useProjectStats";
import { dashboard, memory as memoryApi } from "@/lib/api";
import { formatDistanceToNow } from "@/lib/utils";
import { ActivityChart } from "@/components/dashboard/ActivityChart";
import type { DashboardSummary, DashboardAnalyticsResponse, MemoryEntry } from "@/lib/types";
import { useState, useRef } from "react";
import {
  Plus,
  FolderOpen,
  LayoutGrid,
  Settings,
  FlaskConical,
  FileText,
  GitBranch,
  RefreshCw,
  Brain,
  Search,
  X,
  Loader2,
  Activity,
  LogOut,
  Network,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/components/AuthProvider";

export default function ProjectsPage() {
  const { user, logout } = useAuth();
  const { data: projectList, error, isLoading } = useProjects();
  const { statsMap } = useProjectStats();
  const { data: summaryData } = useSWR<DashboardSummary>(
    "/dashboard/summary",
    () => dashboard.summary(),
    { refreshInterval: 60_000 },
  );
  const { data: analyticsData } = useSWR<DashboardAnalyticsResponse>(
    "/dashboard/analytics",
    () => dashboard.analytics(),
    { refreshInterval: 300_000 },
  );

  const myProjects = (projectList ?? []).filter((p) => p.status !== "demo");
  const demoProjects = (projectList ?? []).filter((p) => p.status === "demo");
  // Build project name lookup for cross-project search results
  const projectNameMap = new Map<string, string>();
  for (const p of projectList ?? []) {
    projectNameMap.set(p.id, p.name);
  }
  const totalDrafts = summaryData?.total_drafts ?? 0;
  const totalSyncs = summaryData?.total_syncs ?? 0;
  const recentActivity = summaryData?.recent_activity ?? [];

  // Global memory search
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryEntry[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleSearch(query: string) {
    setSearchQuery(query);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    searchTimeoutRef.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const results = await memoryApi.searchAll(query, 5);
        setSearchResults(results);
      } catch {
        toast.error("Search failed");
      } finally {
        setIsSearching(false);
      }
    }, 400);
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="border-b border-border">
        <div className="max-w-6xl mx-auto px-8 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">ProjectScribe</h1>
              <p className="text-sm text-muted-foreground mt-1">
                AI co-founder for project management, content, and research
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/projects/new">
                <Button className="gap-2">
                  <Plus className="w-4 h-4" />
                  New Project
                </Button>
              </Link>
              <Link href="/settings">
                <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground" title="Settings">
                  <Settings className="w-4 h-4" />
                </Button>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                className="text-muted-foreground hover:text-foreground"
                title="Sign out"
                onClick={logout}
              >
                <LogOut className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Stats + quick actions */}
          {!isLoading && myProjects.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-5">
              <Link href="/portfolio">
                <Card className="hover:border-primary/50 hover:bg-card/80 transition-all cursor-pointer group">
                  <CardContent className="flex items-center gap-3 p-3">
                    <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                      <LayoutGrid className="w-4 h-4 text-blue-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium group-hover:text-primary transition-colors">Portfolio</p>
                      <p className="text-[11px] text-muted-foreground">Multi-project</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>

              <Link href="/portfolio/paper">
                <Card className="hover:border-primary/50 hover:bg-card/80 transition-all cursor-pointer group">
                  <CardContent className="flex items-center gap-3 p-3">
                    <div className="w-9 h-9 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center shrink-0">
                      <FlaskConical className="w-4 h-4 text-violet-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium group-hover:text-primary transition-colors">Paper</p>
                      <p className="text-[11px] text-muted-foreground">Research</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>

              <Link href="/worklog">
                <Card className="hover:border-primary/50 hover:bg-card/80 transition-all cursor-pointer group">
                  <CardContent className="flex items-center gap-3 p-3">
                    <div className="w-9 h-9 rounded-lg bg-orange-500/10 border border-orange-500/20 flex items-center justify-center shrink-0">
                      <FileText className="w-4 h-4 text-orange-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium group-hover:text-primary transition-colors">Work Log</p>
                      <p className="text-[11px] text-muted-foreground">Reports</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>

              <Link href="/knowledge">
                <Card className="hover:border-primary/50 hover:bg-card/80 transition-all cursor-pointer group">
                  <CardContent className="flex items-center gap-3 p-3">
                    <div className="w-9 h-9 rounded-lg bg-teal-500/10 border border-teal-500/20 flex items-center justify-center shrink-0">
                      <Network className="w-4 h-4 text-teal-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium group-hover:text-primary transition-colors">Knowledge</p>
                      <p className="text-[11px] text-muted-foreground">Cross-project</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>

              <Card className="border-border/50">
                <CardContent className="flex items-center gap-3 p-3">
                  <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                    <GitBranch className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{myProjects.length}</p>
                    <p className="text-[11px] text-muted-foreground">Projects</p>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/50">
                <CardContent className="flex items-center gap-3 p-3">
                  <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-amber-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{totalDrafts}</p>
                    <p className="text-[11px] text-muted-foreground">Drafts</p>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/50">
                <CardContent className="flex items-center gap-3 p-3">
                  <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shrink-0">
                    <RefreshCw className="w-4 h-4 text-cyan-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{totalSyncs}</p>
                    <p className="text-[11px] text-muted-foreground">Syncs</p>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/50">
                <CardContent className="flex items-center gap-3 p-3">
                  <div className="w-9 h-9 rounded-lg bg-pink-500/10 border border-pink-500/20 flex items-center justify-center shrink-0">
                    <Brain className="w-4 h-4 text-pink-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{summaryData?.total_projects ?? 0}</p>
                    <p className="text-[11px] text-muted-foreground">Connected</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Activity chart */}
          {analyticsData && analyticsData.weeks.length > 0 && (
            <div className="mt-5">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Activity (last 12 weeks)
                </h3>
                <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
                  <span>{analyticsData.totals.commits} commits</span>
                  <span>{analyticsData.totals.papers} papers</span>
                  <span>{analyticsData.totals.drafts} drafts</span>
                </div>
              </div>
              <Card className="border-border/50 overflow-hidden">
                <CardContent className="p-4">
                  <ActivityChart data={analyticsData.weeks} height={160} />
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-8 py-8">
        {/* Global memory search */}
        {!isLoading && myProjects.length > 0 && (
          <div className="mb-8">
            <div className="relative max-w-xl">
              {isSearching ? (
                <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground animate-spin" />
              ) : (
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              )}
              <Input
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                placeholder="Search across all project memories..."
                className="pl-9 pr-9 bg-secondary/40"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => { setSearchQuery(""); setSearchResults(null); }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            {searchResults !== null && (
              <div className="mt-3 max-w-xl space-y-2">
                <p className="text-xs text-muted-foreground">
                  {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} across all projects
                </p>
                {searchResults.map((entry) => (
                  <Card key={entry.id} className="border-border/50">
                    <CardContent className="p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="outline" className="text-[10px]">{entry.entry_type}</Badge>
                        {projectNameMap.get(entry.project_id) && (
                          <span className="text-[10px] font-medium text-primary/70">
                            {projectNameMap.get(entry.project_id)}
                          </span>
                        )}
                        <span className="text-[11px] text-muted-foreground">
                          {formatDistanceToNow(entry.created_at)}
                        </span>
                      </div>
                      <p className="text-sm text-foreground/80 line-clamp-2">{entry.content}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {isLoading && (
          <div className="animate-pulse space-y-6">
            <div className="h-4 w-24 bg-secondary rounded" />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-32 bg-secondary/40 rounded-lg" />
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            Failed to load projects: {error.message}
          </div>
        )}

        {!isLoading && !error && projectList?.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center">
              <FolderOpen className="w-8 h-8 text-muted-foreground" />
            </div>
            <div className="text-center">
              <h2 className="text-lg font-medium">No projects yet</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Import your GitHub repos to start generating content.
              </p>
            </div>
            <Link href="/projects/new">
              <Button className="gap-2 mt-2">
                <Plus className="w-4 h-4" />
                Import from GitHub
              </Button>
            </Link>
          </div>
        )}

        {!isLoading && !error && projectList && projectList.length > 0 && (
          <div className="space-y-8">
            {/* Projects grid + activity sidebar */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Projects */}
              <div className="lg:col-span-2 space-y-6">
                {myProjects.length > 0 && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-sm font-medium text-muted-foreground">My Projects</h2>
                      <Badge variant="outline" className="text-xs text-muted-foreground">
                        {myProjects.length} project{myProjects.length !== 1 ? "s" : ""}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {myProjects.map((project) => {
                        const s = statsMap.get(project.id);
                        return (
                          <ProjectCard
                            key={project.id}
                            project={project}
                            lastSyncAt={s?.last_sync_at}
                            draftCount={s?.draft_count}
                          />
                        );
                      })}
                    </div>
                  </div>
                )}
                {demoProjects.length > 0 && (
                  <div>
                    <h2 className="text-sm font-medium text-muted-foreground mb-3">Demo Projects</h2>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 opacity-60">
                      {demoProjects.map((project) => (
                        <ProjectCard key={project.id} project={project} />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Recent activity sidebar */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="w-4 h-4 text-muted-foreground" />
                  <h2 className="text-sm font-medium text-muted-foreground">Recent Activity</h2>
                </div>
                <div className="space-y-1">
                  {recentActivity.length === 0 ? (
                    <p className="text-xs text-muted-foreground py-4 text-center">No recent activity</p>
                  ) : (
                    recentActivity.slice(0, 8).map((item, i) => (
                      <Link
                        key={item.sync_run_id}
                        href={`/projects/${item.project_id}/sync`}
                        className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-secondary/40 transition-colors group"
                      >
                        <div className="w-6 h-6 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shrink-0">
                          <RefreshCw className="w-3 h-3 text-cyan-400" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium truncate group-hover:text-primary transition-colors">
                            {item.project_name}
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            {item.commits_fetched > 0
                              ? `${item.commits_fetched} commit${item.commits_fetched !== 1 ? "s" : ""}`
                              : "Up to date"}
                            {item.completed_at && ` \u00b7 ${formatDistanceToNow(item.completed_at)}`}
                          </p>
                        </div>
                      </Link>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
