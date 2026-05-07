'use client';

import { useState } from 'react';
import { ChevronDown, Plus } from 'lucide-react';
import { useProjects } from '@/lib/hooks/useProjects';

interface ProjectFilterProps {
  projectId: string | undefined;
  onChange: (id: string | undefined) => void;
  onNewProject: () => void;
}

export function ProjectFilter({ projectId, onChange, onNewProject }: ProjectFilterProps) {
  const [open, setOpen] = useState(false);
  const { data: projects = [] } = useProjects();

  const current = projectId ? projects.find((p) => p.id === projectId) : undefined;
  const recent = projects.slice(0, 5);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card/40 px-2.5 py-1.5 text-xs hover:bg-card/60 transition"
      >
        <span className="text-muted-foreground">Project:</span>
        <span className="text-foreground">{current?.name ?? 'All projects'}</span>
        <ChevronDown className="h-3 w-3 text-muted-foreground" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-40 mt-1 w-56 rounded-md border border-border bg-popover p-1 shadow-lg">
            <button
              type="button"
              onClick={() => { onChange(undefined); setOpen(false); }}
              className={`w-full rounded px-2 py-1.5 text-left text-xs ${!projectId ? 'bg-accent text-accent-foreground' : 'hover:bg-muted/40'}`}
            >
              All projects
            </button>

            {recent.length > 0 && (
              <>
                <div className="px-2 pt-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Recent
                </div>
                {recent.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => { onChange(p.id); setOpen(false); }}
                    className={`w-full rounded px-2 py-1.5 text-left text-xs ${projectId === p.id ? 'bg-accent text-accent-foreground' : 'hover:bg-muted/40'}`}
                  >
                    {p.name}
                  </button>
                ))}
              </>
            )}

            <div className="my-1 h-px bg-border" />

            <button
              type="button"
              onClick={() => { onNewProject(); setOpen(false); }}
              className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted/40 hover:text-foreground"
            >
              <Plus className="h-3 w-3" />
              New project
            </button>
          </div>
        </>
      )}
    </div>
  );
}
