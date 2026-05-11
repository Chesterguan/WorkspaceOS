'use client';

import { ChatWindow } from '@/components/chat/ChatWindow';
import { ResearchChatWindow } from '@/components/research/ResearchChatWindow';
import { EmptyProjectPicker } from './EmptyProjectPicker';
import type { RoundtableMode } from '@/lib/bench/useBenchState';

interface Props {
  projectId: string | undefined;
  mode: RoundtableMode;
  onModeChange: (m: RoundtableMode) => void;
}

export function RoundtableSurface({ projectId, mode, onModeChange }: Props) {
  if (!projectId) {
    return (
      <EmptyProjectPicker
        surfaceLabel="conversations"
        hint="Roundtable history is project-scoped. Pick a project to start or continue a conversation."
      />
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <div className="flex items-center gap-2 border-b border-border/40 px-6 py-2">
        <span className="text-xs text-muted-foreground">Mode:</span>
        <button
          type="button"
          onClick={() => onModeChange('cofounder')}
          className={`rounded-md px-2.5 py-1 text-xs ${mode === 'cofounder' ? 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30' : 'text-muted-foreground hover:bg-muted/40'}`}
        >
          Co-Founder
        </button>
        <button
          type="button"
          onClick={() => onModeChange('research')}
          className={`rounded-md px-2.5 py-1 text-xs ${mode === 'research' ? 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30' : 'text-muted-foreground hover:bg-muted/40'}`}
        >
          Research
        </button>
      </div>
      <div className="flex-1 min-h-0">
        {mode === 'cofounder' ? (
          <ChatWindow projectId={projectId} />
        ) : (
          <ResearchChatWindow projectId={projectId} />
        )}
      </div>
    </div>
  );
}
