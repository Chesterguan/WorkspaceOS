import useSWR from 'swr';
import { sync } from '@/lib/api';
import type { SyncRun } from '@/lib/types';

export function useSyncRuns(projectId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<SyncRun[]>(
    projectId ? `/projects/${projectId}/sync` : null,
    () => sync.list(projectId!),
    {
      // Refresh more often when there might be a running sync
      refreshInterval: (data) => {
        const hasRunning = data?.some((r) => r.status === 'running' || r.status === 'pending');
        return hasRunning ? 3000 : 0;
      },
    },
  );

  return { data, error, isLoading, mutate };
}

export function useSyncRun(projectId: string | null, runId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<SyncRun>(
    projectId && runId ? `/projects/${projectId}/sync/${runId}` : null,
    () => sync.get(projectId!, runId!),
    {
      refreshInterval: (data) =>
        data?.status === 'running' || data?.status === 'pending' ? 2000 : 0,
    },
  );

  return { data, error, isLoading, mutate };
}
