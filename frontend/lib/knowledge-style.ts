import type { NodeType, EdgeType } from '@/lib/types';

export const NODE_COLORS: Record<NodeType, string> = {
  claim:      '#3b82f6',
  decision:   '#22c55e',
  question:   '#f59e0b',
  hypothesis: '#a855f7',
  rejection:  '#ef4444',
  blocker:    '#f97316',
  insight:    '#14b8a6',
};

export const EDGE_STYLES: Record<EdgeType, { stroke: string; dashed?: boolean }> = {
  supports:     { stroke: '#22c55e' },
  contradicts:  { stroke: '#ef4444', dashed: true },
  refines:      { stroke: '#3b82f6' },
  follows_up:   { stroke: '#a855f7' },
  depends_on:   { stroke: '#f97316' },
  derives_from: { stroke: '#94a3b8', dashed: true },
  rejects:      { stroke: '#ef4444' },
  related_to:   { stroke: '#94a3b8', dashed: true },
};

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  claim:      'Claim',
  decision:   'Decision',
  question:   'Question',
  hypothesis: 'Hypothesis',
  rejection:  'Rejection',
  blocker:    'Blocker',
  insight:    'Insight',
};
