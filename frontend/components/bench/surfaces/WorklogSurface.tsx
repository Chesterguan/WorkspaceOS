'use client';

import { WorklogContent } from '@/components/worklog/WorklogContent';

interface Props {
  projectId: string | undefined;
}

export function WorklogSurface({ projectId: _projectId }: Props) {
  // WorklogContent has its own internal scope picker (it's natively
  // multi-project). The bench-level project filter is intentionally ignored
  // here — the worklog UI lets users pick which projects to include.
  return (
    <div className="flex-1 overflow-y-auto">
      <WorklogContent />
    </div>
  );
}
