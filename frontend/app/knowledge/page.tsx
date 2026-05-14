'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useKnowledgeNodes } from '@/lib/hooks/useKnowledge';
import type { KnowledgeNode, NodeType } from '@/lib/types';
import { KnowledgeFilters } from '@/components/knowledge/KnowledgeFilters';
import { KnowledgeGraph } from '@/components/knowledge/KnowledgeGraph';
import { NodeDetailPanel } from '@/components/knowledge/NodeDetailPanel';
import { PromoteModal } from '@/components/knowledge/PromoteModal';

export default function KnowledgePage() {
  const [projectId, setProjectId] = useState<string | undefined>();
  const [nodeType, setNodeType] = useState<NodeType | undefined>();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selected, setSelected] = useState<KnowledgeNode | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  const { data: nodes = [], isLoading, mutate } = useKnowledgeNodes({
    projectId,
    nodeType,
    includeArchived,
    limit: 200,
  });

  return (
    <div className="flex h-screen bg-background">
      <KnowledgeFilters
        projectId={projectId}
        onProjectChange={setProjectId}
        nodeType={nodeType}
        onTypeChange={setNodeType}
        includeArchived={includeArchived}
        onIncludeArchivedChange={setIncludeArchived}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <header className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Knowledge</h1>
            <p className="text-sm text-muted-foreground">
              {isLoading
                ? 'Loading…'
                : `${nodes.length} node${nodes.length === 1 ? '' : 's'}`}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setNewOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary text-primary-foreground text-sm font-medium hover:opacity-90"
          >
            <Plus className="w-4 h-4" />
            New
          </button>
        </header>
        <div className="flex-1 relative min-h-0">
          <KnowledgeGraph nodes={nodes} onSelect={setSelected} />
        </div>
        {selected && (
          <NodeDetailPanel
            node={selected}
            allNodes={nodes}
            onClose={() => setSelected(null)}
            onChanged={() => {
              mutate();
              setSelected(null);
            }}
            onSelectNode={(n) => setSelected(n)}
          />
        )}
        <PromoteModal
          open={newOpen}
          source={{ kind: 'manual', note: 'created from /knowledge' }}
          projectId={projectId}
          defaultExcerpt=""
          onClose={() => setNewOpen(false)}
          onSaved={() => {
            mutate();
          }}
        />
      </div>
    </div>
  );
}
