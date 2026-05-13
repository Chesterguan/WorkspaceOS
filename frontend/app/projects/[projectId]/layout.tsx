"use client";

import { use, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useProject } from "@/lib/hooks/useProjects";
import { ProjectSidebar } from "@/components/ProjectSidebar";
import { ProjectHeader } from "@/components/ProjectHeader";
import { ProjectContext } from "@/components/ProjectContext";
import { useDomainConfig } from "@/lib/bench/useDomainConfig";
import { AlertCircle } from "lucide-react";

interface ProjectLayoutProps {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}

export default function ProjectLayout({ children, params }: ProjectLayoutProps) {
  const { projectId } = use(params);
  const pathname = usePathname();
  const { data: project, error, isLoading, mutate } = useProject(projectId);
  const { data: domainConfig } = useDomainConfig();
  const appName = domainConfig?.app?.name ?? "WorkspaceOS";

  // Dynamic page title: "HAVEN | Timeline | <app name>"
  useEffect(() => {
    if (!project) return;
    const segments = pathname.split("/").filter(Boolean);
    // segments: ["projects", projectId, "timeline"] → page = "timeline"
    const page = segments[2] ?? "overview";
    const pageLabel = page.charAt(0).toUpperCase() + page.slice(1);
    document.title = `${project.name} | ${pageLabel} | ${appName}`;
  }, [project, pathname, appName]);

  if (isLoading) {
    return (
      <div className="flex flex-col min-h-screen bg-background animate-pulse">
        {/* Header skeleton */}
        <div className="h-12 border-b border-border bg-card/50" />
        <div className="flex flex-1">
          {/* Sidebar skeleton */}
          <aside className="w-52 shrink-0 border-r border-border bg-sidebar px-2 py-4 space-y-1">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-9 rounded-md bg-secondary/40" />
            ))}
          </aside>
          {/* Content skeleton */}
          <main className="flex-1 p-8 space-y-6">
            <div className="h-8 w-48 bg-secondary rounded" />
            <div className="grid grid-cols-4 gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-24 bg-secondary/40 rounded-lg" />
              ))}
            </div>
            <div className="h-40 bg-secondary/40 rounded-lg" />
          </main>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <div className="w-14 h-14 rounded-full bg-destructive/10 border border-destructive/30 flex items-center justify-center">
          <AlertCircle className="w-7 h-7 text-destructive" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-sm font-medium">
            {error ? "Failed to load project" : "Project not found"}
          </p>
          {error && (
            <p className="text-xs text-muted-foreground">{error.message}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <ProjectContext.Provider value={{ project, mutate }}>
      <div className="flex flex-col min-h-screen bg-background">
        <ProjectHeader project={project} />
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <aside className="w-52 shrink-0 border-r border-border bg-sidebar overflow-y-auto">
            <ProjectSidebar projectId={projectId} />
          </aside>
          {/* Main content */}
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </ProjectContext.Provider>
  );
}
