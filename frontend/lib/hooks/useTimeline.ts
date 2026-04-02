import useSWR from 'swr';
import { sync } from '@/lib/api';
import type { TimelineResponse } from '@/lib/types';

export function useTimeline(projectId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<TimelineResponse>(
    projectId ? `/projects/${projectId}/sync/timeline` : null,
    () => sync.timeline(projectId!),
  );

  return { data, error, isLoading, mutate };
}
