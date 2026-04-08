"use client";

import Image from "next/image";
import { formatDistanceToNow } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { ADVISORS } from "@/lib/advisors";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

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
  const advisorId = message.advisor_id || (message.metadata_?.advisor_id as string | undefined);
  const advisor = advisorId ? ADVISORS[advisorId] : null;

  // Fallback: construct advisor-like object from metadata for research reviewers
  // (their data is stored in metadata_ but not in the ADVISORS registry)
  const reviewerFallback = !advisor && !isUser && message.metadata_?.reviewer_id ? {
    id: (message.metadata_.reviewer_id as string) || "",
    name: (message.metadata_.reviewer_name as string) || "Reviewer",
    tagline: (message.metadata_.modeled_after as string) || "",
    expertise: [],
    color: (message.metadata_.color as string) || "#888",
    avatar: (message.metadata_.avatar as string) || "",
  } : null;
  const displayAdvisor = advisor || reviewerFallback;

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
            <div className="w-5 h-5 rounded-full overflow-hidden border" style={{ borderColor: displayAdvisor.color }}>
              <Image src={displayAdvisor.avatar} alt={displayAdvisor.name} width={20} height={20} className="rounded-full" />
            </div>
            <span className="text-xs font-semibold" style={{ color: displayAdvisor.color }}>{displayAdvisor.name}</span>
          </div>
        ) : (
          <span className="text-xs font-medium text-muted-foreground">
            {isUser ? "You" : "Co-Founder AI"}
          </span>
        )}
        <span className="text-xs text-muted-foreground/60">
          {formatDistanceToNow(message.created_at)}
        </span>
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
