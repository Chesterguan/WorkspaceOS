import useSWR from 'swr';
import { projects } from '@/lib/api';
import type { ProjectStatsItem, ProjectStatsResponse } from '@/lib/types';

/**
 * Fetches draft counts and last sync times for all projects in a single
 * request. The result is indexed by project_id for O(1) lookups in the
 * projects page.
 */
export function useProjectStats() {
  const { data, error, isLoading, mutate } = useSWR<ProjectStatsResponse>(
    '/projects/stats',
    () => projects.stats(),
    {
      // Refresh every 60 seconds — these stats don't need to be real-time
      refreshInterval: 60_000,
    },
  );

  // Build a lookup map: project_id -> stats
  const statsMap = new Map<string, ProjectStatsItem>();
  if (data?.stats) {
    for (const item of data.stats) {
      statsMap.set(item.project_id, item);
    }
  }

  return { statsMap, error, isLoading, mutate };
}
