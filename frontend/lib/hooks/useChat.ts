import useSWR from 'swr';
import { chat } from '@/lib/api';
import type { ChatMessage } from '@/lib/types';

export function useChat(projectId: string) {
  const { data, error, isLoading, mutate } = useSWR<ChatMessage[]>(
    `/projects/${projectId}/chat`,
    async () => {
      const res = await chat.history(projectId);
      return res.messages;
    },
  );

  return { data, error, isLoading, mutate };
}
