import useSWR from 'swr';
import { knowledge } from '@/lib/api';
import type { KnowledgeNode, KnowledgeGraph, NodeType } from '@/lib/types';


export interface UseNodesParams {
  projectId?: string;
  nodeType?: NodeType;
  includeArchived?: boolean;
  limit?: number;
}


export function useKnowledgeNodes(params: UseNodesParams = {}) {
  const key = ['knowledge/nodes', params] as const;
  const { data, error, isLoading, mutate } = useSWR<KnowledgeNode[]>(
    key,
    () => knowledge.listNodes(params),
  );
  return { data, error, isLoading, mutate };
}


export function useKnowledgeGraph(rootId: string | null, depth = 1) {
  const { data, error, isLoading, mutate } = useSWR<KnowledgeGraph>(
    rootId ? ['knowledge/graph', rootId, depth] as const : null,
    () => knowledge.getGraph(rootId!, depth),
  );
  return { data, error, isLoading, mutate };
}
