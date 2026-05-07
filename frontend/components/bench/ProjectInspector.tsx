'use client';

import { X } from 'lucide-react';
import { useProject } from '@/lib/hooks/useProjects';
import type { ReactNode } from 'react';

interface Props {
  projectId: string;
  onClose: () => void;
  children?: ReactNode;
}

export function ProjectInspector({ projectId, onClose, children }: Props) {
  const { data: project } = useProject(projectId);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/60 p-3">
        <div className="text-sm font-semibold text-foreground truncate">
          {project?.name ?? 'Project'}
        </div>
        <button
          type="button"
          aria-label="Close inspector"
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 text-xs">
        {children ?? (
          <div className="text-muted-foreground">(sections will appear in Task 10)</div>
        )}
      </div>
    </div>
  );
}
