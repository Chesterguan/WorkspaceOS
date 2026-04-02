import useSWR from 'swr';
import { memory } from '@/lib/api';
import type { MemoryEntry } from '@/lib/types';

export function useMemory(projectId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<MemoryEntry[]>(
    projectId ? `/projects/${projectId}/memory` : null,
    () => memory.list(projectId!),
  );

  return { data, error, isLoading, mutate };
}
