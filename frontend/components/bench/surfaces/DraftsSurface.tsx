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
  if (!projectId) {
    return <EmptyProjectPicker surfaceLabel="drafts" />;
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { data: items = [], isLoading, mutate } = useSWR<Draft[]>(
    `/projects/${projectId}/drafts`,
    () => draftsApi.list(projectId),
  );

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {isLoading ? (
        <SurfaceLoading rows={4} />
      ) : items.length === 0 ? (
        <div className="text-sm text-muted-foreground">No drafts yet. Click &quot;+ New&quot; in the header.</div>
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
