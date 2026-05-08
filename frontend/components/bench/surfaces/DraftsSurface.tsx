'use client';

import useSWR from 'swr';
import { drafts as draftsApi } from '@/lib/api';
import type { Draft } from '@/lib/types';
import { DraftCard } from '@/components/DraftCard';
import { EmptyProjectPicker } from './EmptyProjectPicker';
import { SurfaceLoading } from '@/components/bench/SurfaceLoading';

interface Props {
  projectId: string | undefined;
}

export function DraftsSurface({ projectId }: Props) {
  // SWR pattern: pass null key when we have no project, and useSWR returns
  // immediately with data: undefined. Hook is always called, so hook count
  // stays consistent across renders regardless of projectId state.
  const { data: items = [], isLoading, mutate } = useSWR<Draft[]>(
    projectId ? `/projects/${projectId}/drafts` : null,
    () => draftsApi.list(projectId!),
  );

  if (!projectId) {
    return <EmptyProjectPicker surfaceLabel="drafts" />;
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {isLoading ? (
        <SurfaceLoading rows={4} />
      ) : items.length === 0 ? (
        <div className="text-sm text-muted-foreground">No drafts yet for this project.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {items.map((d) => (
            <DraftCard
              key={d.id}
              draft={d}
              projectId={projectId}
              onDeleted={() => mutate()}
              onFeedbackRecorded={() => mutate()}
            />
          ))}
        </div>
      )}
    </div>
  );
}
