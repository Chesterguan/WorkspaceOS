import useSWR from 'swr';
import { narratives } from '@/lib/api';
import type { Narrative } from '@/lib/types';

export function useNarrative(projectId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Narrative>(
    projectId ? `/projects/${projectId}/narrative` : null,
    () => narratives.get(projectId!),
  );

  return { data, error, isLoading, mutate };
}
