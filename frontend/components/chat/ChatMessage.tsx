"use client";

import { formatDistanceToNow } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

// Convert basic markdown to HTML for assistant message rendering.
// Handles bold, italic, inline code, code blocks, and line breaks without
// pulling in a full markdown library.
function markdownToHtml(text: string): string {
  let html = text
    // Escape HTML entities first to prevent XSS
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Code blocks (``` ... ```)
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Line breaks (not inside pre blocks — handled separately)
    .replace(/\n/g, '<br />');

  return html;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        "flex flex-col gap-1 animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
        isUser ? "items-end" : "items-start",
      )}
    >
      {/* Role label + timestamp */}
      <div className={cn("flex items-center gap-2 px-1", isUser ? "flex-row-reverse" : "flex-row")}>
        <span className="text-xs font-medium text-muted-foreground">
          {isUser ? "You" : "Co-Founder AI"}
        </span>
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
            : "bg-card text-foreground border border-border rounded-bl-sm",
        )}
      >
        {isUser ? (
          // User messages: plain whitespace-preserved text
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
        ) : (
          // Assistant messages: rendered markdown
          <div
            className="chat-prose break-words"
            dangerouslySetInnerHTML={{ __html: markdownToHtml(message.content) }}
          />
        )}
      </div>
    </div>
  );
}
