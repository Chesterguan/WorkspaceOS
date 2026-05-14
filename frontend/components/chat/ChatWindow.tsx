"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { WorkspaceStatus } from "@/components/chat/WorkspaceStatus";
import { useChat } from "@/lib/hooks/useChat";
import { chat as chatApi, workspace as workspaceApi } from "@/lib/api";
import type { ChatStarterGroup } from "@/lib/api";
import { toast } from "sonner";
import { AdvisorCard } from "@/components/chat/AdvisorCard";
import { RoundtableGroup } from "@/components/chat/RoundtableGroup";
import { usePersonaPool } from "@/lib/personas";
import type { ChatRoundtableResponse } from "@/lib/types";
import { MessageSquare, Send, Loader2, Trash2, Users } from "lucide-react";
import { cn, groupMessages } from "@/lib/utils";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import { ContextPill } from "@/components/chat/ContextPill";
import type { ChatMessage as ChatMessageType, WorkspaceContext, WorkspaceSnapshot } from "@/lib/types";

interface ChatWindowProps {
  projectId: string;
}

// Fallback starters used if the backend request fails
const FALLBACK_STARTERS: ChatStarterGroup[] = [
  {
    category: "Stage & Focus",
    prompts: [
      "What stage is this project at? What should I focus on?",
      "Am I ready to apply to YC with this project?",
    ],
  },
  {
    category: "Business & Revenue",
    prompts: [
      "How should I monetize this project?",
      "What's my addressable market size?",
    ],
  },
  {
    category: "Growth & Users",
    prompts: [
      "How do I get my first 10 users?",
      "What distribution channels should I try?",
    ],
  },
  {
    category: "Pitch & Fundraising",
    prompts: [
      "Help me write a 2-sentence pitch for this project",
      "What questions would a YC partner ask about this?",
    ],
  },
];

export function ChatWindow({ projectId }: ChatWindowProps) {
  const { data: history, isLoading, mutate } = useChat(projectId);
  const { personas: advisors } = usePersonaPool('cofounder');

  // Optimistic messages shown while API call is in-flight
  const [optimisticMessages, setOptimisticMessages] = useState<ChatMessageType[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [inputValue, setInputValue] = useState("");

  // Context toggles — all on by default
  const [includeWorkspace, setIncludeWorkspace] = useState(true);
  const [includeMemory, setIncludeMemory] = useState(true);
  const [includeRepo, setIncludeRepo] = useState(true);
  const [selectedAdvisor, setSelectedAdvisor] = useState<string | null>(null);

  // Workspace context state
  const [workspaceContext, setWorkspaceContext] = useState<WorkspaceContext | null>(null);
  const [lastScannedAt, setLastScannedAt] = useState<string | null>(null);

  // Strategic conversation starters fetched from the backend
  const [starterGroups, setStarterGroups] = useState<ChatStarterGroup[]>(FALLBACK_STARTERS);

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

  // Load initial workspace context
  useEffect(() => {
    workspaceApi.context(projectId)
      .then((ctx) => setWorkspaceContext(ctx))
      .catch(() => {
        // Non-fatal: workspace context is optional
      });
  }, [projectId]);

  // Load strategic conversation starters from backend
  useEffect(() => {
    chatApi.starters()
      .then((groups) => {
        if (groups && groups.length > 0) {
          setStarterGroups(groups);
        }
      })
      .catch(() => {
        // Non-fatal: fall back to the hardcoded starters defined above
      });
  }, []);

  function handleScanned(snapshot: WorkspaceSnapshot) {
    setLastScannedAt(snapshot.scanned_at);
    // Refresh context after a successful scan
    workspaceApi.context(projectId)
      .then((ctx) => setWorkspaceContext(ctx))
      .catch(() => {});
  }

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
      await chatApi.send(projectId, {
        message: messageText,
        advisor_id: selectedAdvisor || undefined,
        include_workspace: includeWorkspace,
        include_memory: includeMemory,
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
  }, [inputValue, isSending, projectId, selectedAdvisor, includeWorkspace, includeMemory, includeRepo, mutate]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleClear() {
    try {
      await chatApi.clear(projectId);
      await mutate();
      toast.success("Conversation cleared");
    } catch (err) {
      toast.error("Failed to clear conversation", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5">
          <MessageSquare className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Co-Founder AI</span>
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/25 text-primary">
            <Users className="w-3 h-3" />
            <span className="text-[10px] font-semibold tracking-wide uppercase">Panel</span>
          </div>
        </div>
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

      {/* Workspace status bar */}
      <WorkspaceStatus
        projectId={projectId}
        context={workspaceContext}
        onScanned={handleScanned}
        lastScannedAt={lastScannedAt}
      />

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : displayMessages.length === 0 && !isSending ? (
          /* Empty state with grouped strategic conversation starters */
          <div className="flex flex-col items-center justify-center h-full gap-6 py-8">
            <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Users className="w-7 h-7 text-primary" />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium">Your advisor panel is ready</p>
              <p className="text-xs text-muted-foreground">
                Ask anything — 3-4 advisors will weigh in from different perspectives, grounded in your actual project data.
              </p>
            </div>

            {/* Grouped starter pills */}
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
                        className="text-left text-sm px-4 py-2.5 rounded-lg border border-border bg-card hover:border-primary/30 hover:bg-primary/5 transition-all text-muted-foreground hover:text-foreground"
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
            {groupMessages(displayMessages).map((item) =>
              item.type === "roundtable" ? (
                <RoundtableGroup
                  key={item.group}
                  messages={item.messages}
                  roundtableGroup={item.group}
                />
              ) : (
                <ChatMessage key={item.message.id} message={item.message} />
              ),
            )}
            {/* Typing indicator while waiting for assistant response */}
            {isSending && <TypingIndicator />}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <Separator />

      {/* Input area */}
      <div className="shrink-0 px-4 py-3 space-y-2">
        {/* Advisor picker */}
        <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-thin">
          <button
            type="button"
            onClick={() => setSelectedAdvisor(null)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-lg border transition-all shrink-0 text-xs font-medium",
              selectedAdvisor === null
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:border-primary/30",
            )}
          >
            <Users className="w-3.5 h-3.5" />
            Panel
          </button>
          {advisors.map((advisor) => (
            <AdvisorCard
              key={advisor.id}
              advisor={advisor}
              size="lg"
              selected={selectedAdvisor === advisor.id}
              onClick={() =>
                setSelectedAdvisor(selectedAdvisor === advisor.id ? null : advisor.id)
              }
            />
          ))}
        </div>

        {/* Context toggles */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground mr-1">Context:</span>
          <ContextPill
            label="Workspace"
            active={includeWorkspace}
            onClick={() => setIncludeWorkspace((v) => !v)}
          />
          <ContextPill
            label="Memory"
            active={includeMemory}
            onClick={() => setIncludeMemory((v) => !v)}
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
            placeholder="Ask the advisor panel… (Enter to send, Shift+Enter for newline)"
            rows={2}
            disabled={isSending}
            className="flex-1 resize-none bg-secondary/30 text-sm min-h-[2.5rem] max-h-40 leading-relaxed transition-all focus-visible:ring-1 focus-visible:ring-primary/50 focus-visible:border-primary/40"
          />
          <Button
            size="icon"
            onClick={() => handleSend()}
            disabled={!inputValue.trim() || isSending}
            className="shrink-0 h-10 w-10"
          >
            {isSending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
