import useSWR from 'swr';
import { research } from '@/lib/api';
import type { ChatMessage } from '@/lib/types';

export function useResearch(projectId: string) {
  const { data, error, isLoading, mutate } = useSWR<ChatMessage[]>(
    projectId ? `/projects/${projectId}/research` : null,
    async () => {
      const res = await research.history(projectId);
      return res.messages;
    },
  );

  return { data, error, isLoading, mutate };
}
