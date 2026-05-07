'use client';

import { useState } from 'react';
import { useKnowledgeNodes } from '@/lib/hooks/useKnowledge';
import type { KnowledgeNode, NodeType } from '@/lib/types';
import { KnowledgeFilters } from '@/components/knowledge/KnowledgeFilters';
import { KnowledgeGraph } from '@/components/knowledge/KnowledgeGraph';
import { NodeDetailPanel } from '@/components/knowledge/NodeDetailPanel';

interface Props {
  projectId: string | undefined;
}

export function KnowledgeSurface({ projectId }: Props) {
  const [nodeType, setNodeType] = useState<NodeType | undefined>();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selected, setSelected] = useState<KnowledgeNode | null>(null);

  const { data: nodes = [], mutate } = useKnowledgeNodes({
    projectId, nodeType, includeArchived, limit: 200,
  });

  return (
    <div className="flex flex-1 min-h-0">
      <div className="hidden lg:block">
        <KnowledgeFilters
          projectId={projectId}
          onProjectChange={() => { /* bench header owns the project filter; ignore */ }}
          nodeType={nodeType}
          onTypeChange={setNodeType}
          includeArchived={includeArchived}
          onIncludeArchivedChange={setIncludeArchived}
        />
      </div>
      <div className="flex flex-1 flex-col min-w-0">
        <div className="flex-1 relative min-h-0">
          <KnowledgeGraph nodes={nodes} onSelect={setSelected} />
        </div>
        {selected && (
          <NodeDetailPanel
            node={selected}
            onClose={() => setSelected(null)}
            onChanged={() => { mutate(); setSelected(null); }}
          />
        )}
      </div>
    </div>
  );
}
