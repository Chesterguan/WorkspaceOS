import useSWR from 'swr';
import { posting } from '@/lib/api';
import type { PostSchedule, PostRecord } from '@/lib/types';

export function usePostSchedules(
  projectId: string | null,
  from?: string,
  to?: string,
) {
  const key = projectId
    ? `/projects/${projectId}/post-schedules${from ? `?from=${from}` : ''}${to ? `&to=${to}` : ''}`
    : null;

  const { data, error, isLoading, mutate } = useSWR<PostSchedule[]>(
    key,
    () => posting.listSchedules(projectId!, from, to),
  );

  return { data, error, isLoading, mutate };
}

export function usePostRecords(projectId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<PostRecord[]>(
    projectId ? `/projects/${projectId}/post-records` : null,
    () => posting.listRecords(projectId!),
  );

  return { data, error, isLoading, mutate };
}
