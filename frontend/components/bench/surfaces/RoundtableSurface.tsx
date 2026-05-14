'use client';

import { ChatWindow } from '@/components/chat/ChatWindow';
import { ResearchChatWindow } from '@/components/research/ResearchChatWindow';
import { EmptyProjectPicker } from './EmptyProjectPicker';

interface Props {
  projectId: string | undefined;
  surfaceId: string;
}

// Each roundtable surface in the domain config maps to one persona pool:
// id=cofounder → ChatWindow (business advisors)
// id=research  → ResearchChatWindow (academic reviewers, paper search)
// A previous version had a Co-Founder/Research mode toggle inside this
// component, but with multiple roundtable surfaces driven by the rail
// the toggle was redundant and silently broke the Research surface
// (defaulting mode to cofounder regardless of which rail entry was clicked).
export function RoundtableSurface({ projectId, surfaceId }: Props) {
  if (!projectId) {
    return (
      <EmptyProjectPicker
        surfaceLabel="conversations"
        hint="Conversations are project-scoped. Pick a project to start or continue one."
      />
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {surfaceId === 'research' ? (
        <ResearchChatWindow projectId={projectId} />
      ) : (
        <ChatWindow projectId={projectId} />
      )}
    </div>
  );
}
