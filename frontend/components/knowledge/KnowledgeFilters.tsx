'use client';

import { useProjects } from '@/lib/hooks/useProjects';
import { useKnowledgeTaxonomy } from '@/lib/knowledge-style';
import type { NodeType } from '@/lib/types';

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
  const taxonomy = useKnowledgeTaxonomy();
  const nodeTypes = taxonomy?.node_types ?? [];

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
          {nodeTypes.map((nt) => (
            <label key={nt.id} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="nodeType"
                checked={nodeType === nt.id}
                onChange={() => onTypeChange(nt.id)}
              />
              <span>{nt.label}</span>
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
