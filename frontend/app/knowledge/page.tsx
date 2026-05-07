'use client';

import { useState } from 'react';
import { useKnowledgeNodes } from '@/lib/hooks/useKnowledge';
import type { KnowledgeNode, NodeType } from '@/lib/types';
import { KnowledgeFilters } from '@/components/knowledge/KnowledgeFilters';
import { KnowledgeGraph } from '@/components/knowledge/KnowledgeGraph';
import { NodeDetailPanel } from '@/components/knowledge/NodeDetailPanel';

export default function KnowledgePage() {
  const [projectId, setProjectId] = useState<string | undefined>();
  const [nodeType, setNodeType] = useState<NodeType | undefined>();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selected, setSelected] = useState<KnowledgeNode | null>(null);

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
        <header className="px-6 py-4 border-b">
          <h1 className="text-2xl font-semibold">Knowledge</h1>
          <p className="text-sm text-muted-foreground">
            {isLoading
              ? 'Loading…'
              : `${nodes.length} node${nodes.length === 1 ? '' : 's'}`}
          </p>
        </header>
        <div className="flex-1 relative min-h-0">
          <KnowledgeGraph nodes={nodes} onSelect={setSelected} />
        </div>
        {selected && (
          <NodeDetailPanel
            node={selected}
            onClose={() => setSelected(null)}
            onChanged={() => {
              mutate();
              setSelected(null);
            }}
          />
        )}
      </div>
    </div>
  );
}
