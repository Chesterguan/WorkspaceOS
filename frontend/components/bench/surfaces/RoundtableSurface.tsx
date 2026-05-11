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
      <div className="flex items-center gap-3 border-b border-border/40 px-6 py-2">
        <span className="text-xs text-muted-foreground">Mode:</span>
        <div
          role="tablist"
          aria-label="Roundtable mode"
          className="inline-flex rounded-md border border-border bg-card/40 p-0.5"
        >
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'cofounder'}
            onClick={() => onModeChange('cofounder')}
            className={`rounded px-3 py-1 text-xs font-medium transition ${
              mode === 'cofounder'
                ? 'bg-violet-500/25 text-violet-200 ring-1 ring-violet-500/40 shadow-sm'
                : 'text-foreground/80 hover:bg-muted/40 hover:text-foreground'
            }`}
          >
            Co-Founder
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'research'}
            onClick={() => onModeChange('research')}
            className={`rounded px-3 py-1 text-xs font-medium transition ${
              mode === 'research'
                ? 'bg-violet-500/25 text-violet-200 ring-1 ring-violet-500/40 shadow-sm'
                : 'text-foreground/80 hover:bg-muted/40 hover:text-foreground'
            }`}
          >
            Research
          </button>
        </div>
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
