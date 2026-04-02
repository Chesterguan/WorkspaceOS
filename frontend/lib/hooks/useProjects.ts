import useSWR from 'swr';
import { projects } from '@/lib/api';
import type { Project } from '@/lib/types';

export function useProjects() {
  const { data, error, isLoading, mutate } = useSWR<Project[]>(
    '/projects',
    () => projects.list(),
  );

  return { data, error, isLoading, mutate };
}

export function useProject(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Project>(
    id ? `/projects/${id}` : null,
    () => projects.get(id!),
  );

  return { data, error, isLoading, mutate };
}
