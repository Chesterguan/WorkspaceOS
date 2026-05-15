'use client';

import Link from 'next/link';
import { FolderPlus, Plug, ArrowUpRight } from 'lucide-react';

interface Props {
  surfaceLabel: string;
  hint?: string;
}

// Shown whenever no project is selected. For a brand-new user this is
// the first thing they see after onboarding, and the old version was a
// dead-end ("Pick a project" — but there are no projects, and no way
// to make one or connect data from here). It's now a launchpad: the
// two things a fresh user actually needs to do are one click away.
export function EmptyProjectPicker({ surfaceLabel, hint }: Props) {
  return (
    <div className="flex flex-1 items-center justify-center p-12 text-center">
      <div className="max-w-md space-y-5">
        <div className="space-y-1.5">
          <div className="text-base text-foreground">
            Pick a project to see {surfaceLabel.toLowerCase()}.
          </div>
          <p className="text-xs text-muted-foreground">
            {hint ??
              `${surfaceLabel} are project-scoped. Use the project filter in the top right of the page header.`}
          </p>
        </div>

        <div className="space-y-2 text-left">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70 text-center">
            New here? Start with these
          </p>
          <Link
            href="/projects/new"
            className="flex items-center gap-3 rounded-lg border border-border/60 bg-card/40 px-4 py-3 hover:border-violet-500/50 hover:bg-violet-500/5 transition-colors"
          >
            <FolderPlus className="h-4 w-4 text-violet-400 shrink-0" />
            <div>
              <div className="text-sm font-medium text-foreground">Create your first project</div>
              <div className="text-[11px] text-muted-foreground">
                A project is the home for your experiments, papers, and conversations.
              </div>
            </div>
          </Link>
          <Link
            href="/settings"
            className="flex items-center gap-3 rounded-lg border border-border/60 bg-card/40 px-4 py-3 hover:border-violet-500/50 hover:bg-violet-500/5 transition-colors"
          >
            <Plug className="h-4 w-4 text-violet-400 shrink-0" />
            <div>
              <div className="text-sm font-medium text-foreground">Connect your tools</div>
              <div className="text-[11px] text-muted-foreground">
                Link Benchling, GitHub, or preprint feeds so the bench has your data to work with.
              </div>
            </div>
          </Link>
        </div>

        <ArrowUpRight className="mx-auto h-5 w-5 text-muted-foreground/60" />
      </div>
    </div>
  );
}
