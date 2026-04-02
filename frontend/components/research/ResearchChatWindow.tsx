"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { PaperSearchDialog } from "@/components/research/PaperSearchDialog";
import { useResearch } from "@/lib/hooks/useResearch";
import { research as researchApi } from "@/lib/api";
import { toast } from "sonner";
import {
  BookOpen,
  Send,
  Loader2,
  Trash2,
  Search,
  FlaskConical,
  FileText,
} from "lucide-react";
import { cn, formatDistanceToNow } from "@/lib/utils";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

interface ResearchChatWindowProps {
  projectId: string;
}

interface StarterGroup {
  category: string;
  prompts: string[];
}

// Fallback starters if the backend endpoint is unavailable
const FALLBACK_STARTERS: StarterGroup[] = [
  {
    category: "Literature",
    prompts: [
      "What are the key papers on transformer architectures I should read?",
      "Summarize the state of the art in retrieval-augmented generation",
    ],
  },
  {
    category: "Writing",
    prompts: [
      "Help me write the related works section for my paper",
      "How should I frame my contributions relative to prior work?",
    ],
  },
  {
    category: "Proposals",
    prompts: [
      "Help me draft a research proposal for this project",
      "What research gaps does my project address?",
    ],
  },
  {
    category: "Strategy",
    prompts: [
      "What venues should I target to publish this research?",
      "How do I strengthen the novelty claim of my approach?",
    ],
  },
];

// Context toggle pill — matches the style from ChatWindow exactly
function ContextPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-3 py-1 rounded-full text-xs font-medium border transition-all select-none",
        active
          ? "bg-violet-500/15 text-violet-400 border-violet-500/40"
          : "border-border text-muted-foreground hover:border-border/80 hover:text-foreground/70",
      )}
    >
      {label}
    </button>
  );
}

// Animated typing indicator shown while waiting for the AI response
function TypingIndicator() {
  return (
    <div className="flex items-start gap-1 animate-in fade-in-0 duration-200">
      <div className="bg-card border border-border rounded-lg rounded-bl-sm px-4 py-3 flex items-center gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
}

export function ResearchChatWindow({ projectId }: ResearchChatWindowProps) {
  const { data: history, isLoading, mutate } = useResearch(projectId);

  // Optimistic messages shown while API call is in-flight
  const [optimisticMessages, setOptimisticMessages] = useState<ChatMessageType[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [inputValue, setInputValue] = useState("");

  // Research-specific context toggles
  const [includeLiterature, setIncludeLiterature] = useState(true);
  const [includeWorkspace, setIncludeWorkspace] = useState(true);
  const [includeRepo, setIncludeRepo] = useState(true);

  // Paper search dialog state
  const [searchDialogOpen, setSearchDialogOpen] = useState(false);

  // Conversation starters fetched from backend
  const [starterGroups, setStarterGroups] = useState<StarterGroup[]>(FALLBACK_STARTERS);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Combine fetched history with any in-flight optimistic messages
  const displayMessages: ChatMessageType[] = [
    ...(history ?? []),
    ...optimisticMessages,
  ];

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages.length, isSending]);

  // Load research conversation starters from backend
  useEffect(() => {
    researchApi.starters()
      .then((groups) => {
        if (groups && groups.length > 0) {
          setStarterGroups(groups);
        }
      })
      .catch(() => {
        // Non-fatal: fall back to the hardcoded starters defined above
      });
  }, []);

  // Auto-resize textarea as the user types
  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  const handleSend = useCallback(async (text?: string) => {
    const messageText = (text ?? inputValue).trim();
    if (!messageText || isSending) return;

    // Build optimistic user message so it appears immediately
    const tempUserMsg: ChatMessageType = {
      id: `temp-user-${Date.now()}`,
      project_id: projectId,
      role: "user",
      content: messageText,
      created_at: new Date().toISOString(),
    };

    setOptimisticMessages([tempUserMsg]);
    setInputValue("");
    setIsSending(true);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    try {
      await researchApi.send(projectId, {
        message: messageText,
        include_literature: includeLiterature,
        include_workspace: includeWorkspace,
        include_repo: includeRepo,
      });

      // Refresh the full history from the server (includes the real IDs)
      await mutate();
      setOptimisticMessages([]);
    } catch (err) {
      // Remove the optimistic message on error so the user can retry
      setOptimisticMessages([]);
      toast.error("Failed to send message", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSending(false);
    }
  }, [inputValue, isSending, projectId, includeLiterature, includeWorkspace, includeRepo, mutate]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleClear() {
    try {
      await researchApi.clear(projectId);
      await mutate();
      toast.success("Research conversation cleared");
    } catch (err) {
      toast.error("Failed to clear conversation", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  // Called when the user clicks "Use in chat" in the paper search dialog.
  // Appends the citation string to the current input value.
  function handleUsePaper(citationString: string) {
    const prefix = inputValue.trim() ? `${inputValue.trim()}\n\n` : "";
    setInputValue(`${prefix}${citationString}`);
    // Trigger textarea resize after state update
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
        textareaRef.current.focus();
      }
    }, 0);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5">
          <BookOpen className="w-4 h-4 text-violet-400" />
          <span className="text-sm font-semibold">Research Assistant</span>
          {/* ARIS-Powered badge in violet/purple tones */}
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/25 text-violet-500 dark:text-violet-400">
            <FlaskConical className="w-3 h-3" />
            <span className="text-[10px] font-semibold tracking-wide uppercase">ARIS-Powered</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Write paper shortcut */}
          <Link href={`/projects/${projectId}/research/paper`}>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs border-violet-500/30 text-violet-400 hover:bg-violet-500/10 hover:text-violet-300 gap-1.5"
            >
              <FileText className="w-3.5 h-3.5" />
              Write Paper
            </Button>
          </Link>
          {/* Paper search button in header */}
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs border-violet-500/30 text-violet-400 hover:bg-violet-500/10 hover:text-violet-300 gap-1.5"
            onClick={() => setSearchDialogOpen(true)}
          >
            <Search className="w-3.5 h-3.5" />
            Search Papers
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground hover:text-destructive gap-1.5"
            onClick={handleClear}
            disabled={isSending}
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </Button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : displayMessages.length === 0 && !isSending ? (
          /* Empty state with grouped research conversation starters */
          <div className="flex flex-col items-center justify-center h-full gap-6 py-8">
            <div className="w-14 h-14 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
              <BookOpen className="w-7 h-7 text-violet-500" />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium">Your research assistant is ready</p>
              <p className="text-xs text-muted-foreground">
                Search literature, draft sections, refine proposals, or discuss research strategy — grounded in your project context.
              </p>
            </div>

            {/* Grouped research starter prompts */}
            <div className="w-full max-w-lg space-y-4">
              {starterGroups.map((group) => (
                <div key={group.category} className="space-y-1.5">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 px-1">
                    {group.category}
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {group.prompts.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => handleSend(prompt)}
                        className="text-left text-sm px-4 py-2.5 rounded-lg border border-border bg-card hover:border-violet-500/30 hover:bg-violet-500/5 transition-all text-muted-foreground hover:text-foreground"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            {displayMessages.map((msg) => (
              <ResearchChatMessage key={msg.id} message={msg} />
            ))}
            {/* Typing indicator while waiting for assistant response */}
            {isSending && <TypingIndicator />}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <Separator />

      {/* Input area */}
      <div className="shrink-0 px-4 py-3 space-y-2">
        {/* Context toggles — Literature is an extra toggle unique to Research */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground mr-1">Context:</span>
          <ContextPill
            label="Literature Search"
            active={includeLiterature}
            onClick={() => setIncludeLiterature((v) => !v)}
          />
          <ContextPill
            label="Workspace"
            active={includeWorkspace}
            onClick={() => setIncludeWorkspace((v) => !v)}
          />
          <ContextPill
            label="Repo"
            active={includeRepo}
            onClick={() => setIncludeRepo((v) => !v)}
          />
        </div>

        {/* Textarea + send button */}
        <div className="flex gap-2 items-end">
          <Textarea
            ref={textareaRef}
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask the Research Assistant… (Enter to send, Shift+Enter for newline)"
            rows={2}
            disabled={isSending}
            className="flex-1 resize-none bg-secondary/30 text-sm min-h-[2.5rem] max-h-40 leading-relaxed transition-all focus-visible:ring-1 focus-visible:ring-violet-500/50 focus-visible:border-violet-500/40"
          />
          <Button
            size="icon"
            onClick={() => handleSend()}
            disabled={!inputValue.trim() || isSending}
            className="shrink-0 h-10 w-10 bg-violet-600 hover:bg-violet-700 text-white"
          >
            {isSending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Paper search dialog */}
      <PaperSearchDialog
        projectId={projectId}
        open={searchDialogOpen}
        onOpenChange={setSearchDialogOpen}
        onUsePaper={handleUsePaper}
      />
    </div>
  );
}

// ─── ResearchChatMessage ──────────────────────────────────────────────────────
// Extends the base ChatMessage with citation rendering for academic text.
// When the assistant message contains [1], [2]… citation markers, they are
// highlighted visually to signal that paper references are present.

interface ResearchChatMessageProps {
  message: ChatMessageType;
}

// Escape HTML entities to prevent XSS before further processing
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Convert markdown to HTML — matches the lightweight renderer in ChatMessage
// but also highlights inline citation markers like [1], [2], [1,2], etc.
function researchMarkdownToHtml(text: string): string {
  let html = escapeHtml(text)
    // Code blocks
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    // Citation markers like [1], [2,3], [1–3] — styled as violet badges
    .replace(
      /\[(\d[\d,\s–\-]*)\]/g,
      '<sup class="inline-flex items-baseline"><span class="inline-block px-1 py-0.5 rounded text-[10px] font-semibold bg-violet-500/15 text-violet-400 border border-violet-500/30 leading-none mx-0.5">[$1]</span></sup>',
    )
    // Line breaks
    .replace(/\n/g, "<br />");

  return html;
}

function ResearchChatMessage({ message }: ResearchChatMessageProps) {
  const isUser = message.role === "user";

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
          {isUser ? "You" : "Research Assistant"}
        </span>
        <span className="text-xs text-muted-foreground/60">
          {formatDistanceToNow(message.created_at)}
        </span>
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm",
          // Slightly more generous line spacing for academic text
          "leading-7",
          isUser
            ? "bg-violet-500/10 text-foreground border border-violet-500/20 rounded-br-sm shadow-sm"
            : "bg-card text-foreground border border-border rounded-bl-sm",
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
        ) : (
          <div
            className="chat-prose break-words"
            dangerouslySetInnerHTML={{ __html: researchMarkdownToHtml(message.content) }}
          />
        )}
      </div>
    </div>
  );
}
