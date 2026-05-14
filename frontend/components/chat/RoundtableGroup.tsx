'use client';

import { PersonaAvatar } from '@/components/personas/PersonaAvatar';
import { ChatMessage } from '@/components/chat/ChatMessage';
import { usePersonaPool } from '@/lib/personas';
import type { ChatMessage as ChatMessageType } from '@/lib/types';
import { Users } from 'lucide-react';

interface RoundtableGroupProps {
  messages: ChatMessageType[];
  roundtableGroup: string;
}

interface Participant {
  id: string;
  name: string;
  color: string;
  avatar: string;
}

export function RoundtableGroup({ messages }: RoundtableGroupProps) {
  // Cofounder pool drives the lookup. Research reviewers fall through to
  // the metadata-derived fallback below — they're not in this pool, but
  // their messages carry name/avatar in metadata fields.
  const { byId: cofounderById } = usePersonaPool('cofounder');
  const { byId: researchById } = usePersonaPool('research');

  // Build the participant list from each message: prefer the persona
  // pool record, fall back to message metadata for surfaces / personas
  // we don't currently have in config (legacy data, custom integrations).
  const participants: Participant[] = messages
    .map((m): Participant | null => {
      const advisorId = m.advisor_id || (m.metadata_?.advisor_id as string | undefined);
      if (advisorId) {
        const p = cofounderById[advisorId] ?? researchById[advisorId];
        if (p) return { id: p.id, name: p.name, color: p.color, avatar: p.avatar };
      }
      const reviewerId = m.metadata_?.reviewer_id as string | undefined;
      if (reviewerId) {
        const p = researchById[reviewerId];
        if (p) return { id: p.id, name: p.name, color: p.color, avatar: p.avatar };
        return {
          id: reviewerId,
          name: (m.metadata_?.reviewer_name as string) || reviewerId,
          color: '#a78bfa',
          avatar: (m.metadata_?.avatar as string) || '',
        };
      }
      return null;
    })
    .filter((p): p is Participant => p !== null);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <Users className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Panel
        </span>
        <div className="flex -space-x-1.5">
          {participants.map((p) => (
            <div
              key={p.id}
              title={p.name}
              className="rounded-full border border-background overflow-hidden"
            >
              <PersonaAvatar
                name={p.name}
                color={p.color}
                avatar={p.avatar}
                size={20}
              />
            </div>
          ))}
        </div>
        <span className="text-[10px] text-muted-foreground">
          {participants.length} {participants.length === 1 ? 'advisor' : 'advisors'} weighed in
        </span>
      </div>
      <div className="space-y-3 border-l-2 border-border/50 pl-3 ml-1">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  );
}
