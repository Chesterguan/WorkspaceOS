"use client";

import Image from "next/image";
import { ADVISORS } from "@/lib/advisors";
import { ChatMessage } from "@/components/chat/ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import { Users } from "lucide-react";

interface RoundtableGroupProps {
  messages: ChatMessageType[];
  roundtableGroup: string;
}

export function RoundtableGroup({ messages, roundtableGroup }: RoundtableGroupProps) {
  // Collect advisor/reviewer display info from each message
  const participants = messages
    .map((m) => {
      const advisorId = m.advisor_id || (m.metadata_?.advisor_id as string | undefined);
      if (advisorId && ADVISORS[advisorId]) {
        const a = ADVISORS[advisorId];
        return { id: advisorId, name: a.name, avatar: a.avatar };
      }
      // Fallback for research reviewers: read from metadata
      const reviewerId = m.metadata_?.reviewer_id as string | undefined;
      if (reviewerId) {
        return {
          id: reviewerId,
          name: (m.metadata_?.reviewer_name as string) || reviewerId,
          avatar: (m.metadata_?.avatar as string) || "",
        };
      }
      return null;
    })
    .filter((p): p is { id: string; name: string; avatar: string } => p !== null);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <Users className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Roundtable
        </span>
        <div className="flex -space-x-1.5">
          {participants.map((p) => (
            <div key={p.id} className="w-5 h-5 rounded-full overflow-hidden border border-background" title={p.name}>
              {p.avatar ? (
                <Image src={p.avatar} alt={p.name} width={20} height={20} />
              ) : (
                <div className="w-5 h-5 bg-muted rounded-full" />
              )}
            </div>
          ))}
        </div>
        <span className="text-[10px] text-muted-foreground">
          {participants.length} {participants.length === 1 ? "advisor" : "advisors"} weighed in
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
