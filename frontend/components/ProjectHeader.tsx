"use client";

import Link from "next/link";
import { ExternalLink, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Project } from "@/lib/types";

interface ProjectHeaderProps {
  project: Project;
}

export function ProjectHeader({ project }: ProjectHeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-background/80 backdrop-blur-sm sticky top-0 z-10">
      <div className="flex items-center gap-3">
        <Link href="/projects">
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground">
            <ChevronLeft className="w-4 h-4" />
            Projects
          </Button>
        </Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-sm font-semibold">{project.name}</span>
      </div>

      {project.github_repo && (
        <a
          href={`https://github.com/${project.github_repo}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground text-xs">
            <ExternalLink className="w-3.5 h-3.5" />
            {project.github_repo}
          </Button>
        </a>
      )}
    </header>
  );
}
