"use client";

import { formatDistanceToNow } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { PersonaAvatar } from "@/components/personas/PersonaAvatar";
import { usePersonaPool } from "@/lib/personas";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import { PromoteButton } from "@/components/knowledge/PromoteButton";

interface ChatMessageProps {
  message: ChatMessageType;
}

function markdownToHtml(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br />');
  return html;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const { byId: cofounderById } = usePersonaPool('cofounder');
  const { byId: researchById } = usePersonaPool('research');

  const advisorId = message.advisor_id || (message.metadata_?.advisor_id as string | undefined);
  const fromPool = advisorId
    ? (cofounderById[advisorId] ?? researchById[advisorId] ?? null)
    : null;

  // Research reviewer messages carry their info in metadata_. If the
  // reviewer_id isn't in the live persona pool (e.g. message predates
  // a config change), reconstruct a display-only persona from metadata.
  const reviewerId = message.metadata_?.reviewer_id as string | undefined;
  const reviewerFromPool = reviewerId ? researchById[reviewerId] ?? null : null;
  const reviewerFallback = !fromPool && !reviewerFromPool && !isUser && reviewerId ? {
    id: reviewerId,
    name: (message.metadata_?.reviewer_name as string) || "Reviewer",
    color: (message.metadata_?.color as string) || "#888",
    avatar: (message.metadata_?.avatar as string) || "",
  } : null;

  const displayAdvisor = fromPool ?? reviewerFromPool ?? reviewerFallback;

  return (
    <div
      className={cn(
        "flex flex-col gap-1 animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
        isUser ? "items-end" : "items-start",
      )}
    >
      {/* Role label + timestamp */}
      <div className={cn("flex items-center gap-2 px-1", isUser ? "flex-row-reverse" : "flex-row")}>
        {displayAdvisor && !isUser ? (
          <div className="flex items-center gap-1.5">
            <div className="rounded-full overflow-hidden border" style={{ borderColor: displayAdvisor.color }}>
              <PersonaAvatar
                name={displayAdvisor.name}
                color={displayAdvisor.color}
                avatar={displayAdvisor.avatar}
                size={20}
              />
            </div>
            <span className="text-xs font-semibold" style={{ color: displayAdvisor.color }}>
              {displayAdvisor.name}
            </span>
          </div>
        ) : (
          <span className="text-xs font-medium text-muted-foreground">
            {isUser ? "You" : "Co-Founder AI"}
          </span>
        )}
        <span className="text-xs text-muted-foreground/60">
          {formatDistanceToNow(message.created_at)}
        </span>
        {!isUser && (
          <PromoteButton
            source={{
              kind: 'chat_message',
              id: message.id,
              excerpt: message.content.slice(0, 200),
            }}
            projectId={message.project_id}
            defaultExcerpt={message.content.slice(0, 600)}
            className="opacity-40 hover:opacity-100 transition w-5 h-5 inline-flex items-center justify-center rounded text-muted-foreground hover:bg-muted"
          />
        )}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-primary/15 text-foreground border border-primary/25 rounded-br-sm shadow-sm"
            : "bg-card text-foreground border rounded-bl-sm",
        )}
        style={
          displayAdvisor && !isUser
            ? { borderColor: `${displayAdvisor.color}30`, borderLeftWidth: "3px", borderLeftColor: displayAdvisor.color }
            : { borderColor: "var(--border)" }
        }
      >
        {isUser ? (
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
        ) : (
          <div
            className="chat-prose break-words"
            dangerouslySetInnerHTML={{ __html: markdownToHtml(message.content) }}
          />
        )}
      </div>
    </div>
  );
}
