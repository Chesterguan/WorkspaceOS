import { useDomainConfig } from '@/lib/bench/useDomainConfig';
import type {
  DomainConfigTaxonomy,
  EdgeType,
  NodeType,
} from '@/lib/types';

// Fallbacks used when no taxonomy is loaded yet or no graph surface is configured.
const FALLBACK_NODE_COLOR = '#888';
const FALLBACK_EDGE_STROKE = '#888';

export function nodeColor(taxonomy: DomainConfigTaxonomy | undefined, type: NodeType): string {
  const nt = taxonomy?.node_types.find((n) => n.id === type);
  return nt?.color ?? FALLBACK_NODE_COLOR;
}

export function nodeLabel(taxonomy: DomainConfigTaxonomy | undefined, type: NodeType): string {
  const nt = taxonomy?.node_types.find((n) => n.id === type);
  return nt?.label ?? type;
}

export function edgeStyle(
  taxonomy: DomainConfigTaxonomy | undefined,
  type: EdgeType,
): { stroke: string; dashed: boolean } {
  const et = taxonomy?.edge_types.find((e) => e.id === type);
  return {
    stroke: et?.stroke ?? FALLBACK_EDGE_STROKE,
    dashed: et?.style === 'dashed',
  };
}

/**
 * Returns the active taxonomy for the first `graph`-type surface (i.e. the
 * knowledge surface in the default preset). Returns undefined until the
 * config is loaded — callers should fall back gracefully via the helpers above.
 */
export function useKnowledgeTaxonomy(): DomainConfigTaxonomy | undefined {
  const { data } = useDomainConfig();
  return data?.surfaces.find((s) => s.type === 'graph')?.taxonomy;
}
