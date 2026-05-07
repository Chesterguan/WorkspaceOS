'use client';

import { useProjects } from '@/lib/hooks/useProjects';
import type { NodeType } from '@/lib/types';
import { NODE_TYPE_LABELS } from '@/lib/knowledge-style';

const NODE_TYPES: NodeType[] = [
  'claim', 'decision', 'question', 'hypothesis',
  'rejection', 'blocker', 'insight',
];

interface Props {
  projectId: string | undefined;
  onProjectChange: (id: string | undefined) => void;
  nodeType: NodeType | undefined;
  onTypeChange: (t: NodeType | undefined) => void;
  includeArchived: boolean;
  onIncludeArchivedChange: (v: boolean) => void;
}

export function KnowledgeFilters({
  projectId,
  onProjectChange,
  nodeType,
  onTypeChange,
  includeArchived,
  onIncludeArchivedChange,
}: Props) {
  const { data: projects = [] } = useProjects();

  return (
    <aside className="w-64 shrink-0 border-r p-4 space-y-6 bg-card overflow-y-auto">
      <div>
        <label className="text-sm font-medium block mb-1">Project</label>
        <select
          className="w-full p-2 rounded border bg-background text-sm"
          value={projectId ?? ''}
          onChange={(e) => onProjectChange(e.target.value || undefined)}
        >
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      <fieldset>
        <legend className="text-sm font-medium block mb-1">Type</legend>
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="nodeType"
              checked={!nodeType}
              onChange={() => onTypeChange(undefined)}
            />
            <span>All</span>
          </label>
          {NODE_TYPES.map((t) => (
            <label key={t} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="nodeType"
                checked={nodeType === t}
                onChange={() => onTypeChange(t)}
              />
              <span>{NODE_TYPE_LABELS[t]}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeArchived}
          onChange={(e) => onIncludeArchivedChange(e.target.checked)}
        />
        <span>Show archived</span>
      </label>
    </aside>
  );
}
