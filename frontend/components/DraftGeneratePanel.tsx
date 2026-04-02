"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Sparkles,
  Loader2,
  ChevronDown,
  ChevronUp,
  Bot,
  Zap,
  Shield,
  Eye,
  Pen,
  Check,
  Circle,
} from "lucide-react";
import { ai } from "@/lib/api";
import { toast } from "sonner";
import { useSyncRuns } from "@/lib/hooks/useSyncRuns";
import type { Platform, SyncRun, AgenticLoopStep } from "@/lib/types";
import { PLATFORM_LABELS } from "@/components/PlatformBadge";
import { cn } from "@/lib/utils";

const PLATFORMS: Platform[] = [
  "linkedin",
  "twitter",
  "xiaohongshu",
  "medium_outline",
  "github_release",
];

// Pipeline stages for the agentic mode
const PIPELINE_STAGES = [
  { id: "generate", label: "Generating draft", icon: Pen, model: "Gemini Flash" },
  { id: "privacy", label: "Privacy scan", icon: Shield, model: "Local (Ollama)" },
  { id: "review", label: "Review & score", icon: Eye, model: "GPT-4o" },
  { id: "revise", label: "Revising draft", icon: Pen, model: "Gemini Flash" },
  { id: "done", label: "Complete", icon: Check, model: "" },
];

interface DraftGeneratePanelProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onGenerated?: (draftId: string) => void;
}

export function DraftGeneratePanel({
  projectId,
  open,
  onOpenChange,
  onGenerated,
}: DraftGeneratePanelProps) {
  const router = useRouter();
  const { data: syncRuns } = useSyncRuns(projectId);
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [syncRunId, setSyncRunId] = useState<string>("");
  const [additionalContext, setAdditionalContext] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [mode, setMode] = useState<"standard" | "agentic">("standard");

  // Progress state
  const [currentStage, setCurrentStage] = useState(0);
  const [currentRound, setCurrentRound] = useState(0);
  const [maxRounds] = useState(4);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Trace
  const [loopTrace, setLoopTrace] = useState<AgenticLoopStep[] | null>(null);
  const [traceExpanded, setTraceExpanded] = useState(false);

  const completedRuns = (syncRuns ?? []).filter((r: SyncRun) => r.status === "completed");

  // Elapsed timer
  useEffect(() => {
    if (isGenerating) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isGenerating]);

  // Simulate stage progression based on timing
  // Real timing: generate ~3s, privacy ~5s, review ~3s, revise ~3s per round
  useEffect(() => {
    if (!isGenerating || mode !== "agentic") return;

    setCurrentStage(0);
    setCurrentRound(1);

    const stages = [
      { delay: 0, stage: 0 },      // generating
      { delay: 3000, stage: 1 },    // privacy scan
      { delay: 8000, stage: 2 },    // review
      { delay: 11000, stage: 3 },   // revise (round 1 done)
    ];

    const timeouts: ReturnType<typeof setTimeout>[] = [];

    // Set up round progression
    let baseDelay = 0;
    for (let round = 1; round <= maxRounds; round++) {
      for (const s of stages) {
        const t = setTimeout(() => {
          setCurrentStage(s.stage);
          setCurrentRound(round);
        }, baseDelay + s.delay);
        timeouts.push(t);
      }
      baseDelay += 14000; // ~14s per round
    }

    return () => {
      timeouts.forEach(clearTimeout);
    };
  }, [isGenerating, mode, maxRounds]);

  async function handleGenerate() {
    setIsGenerating(true);
    setLoopTrace(null);
    setCurrentStage(0);
    setCurrentRound(0);
    try {
      if (mode === "agentic") {
        const result = await ai.generateAgentic(projectId, {
          platform,
          sync_run_id: syncRunId || undefined,
          additional_context: additionalContext || undefined,
        });
        setCurrentStage(4); // done
        setLoopTrace(result.loop_trace ?? null);
        toast.success("Draft generated!", {
          description: `Agentic ${PLATFORM_LABELS[platform]} draft — ${(result.loop_trace ?? []).length} rounds`,
        });
        onOpenChange(false);
        if (onGenerated) {
          onGenerated(result.draft_id);
        } else {
          router.push(`/projects/${projectId}/drafts/${result.draft_id}`);
        }
      } else {
        const result = await ai.generate(projectId, {
          platform,
          sync_run_id: syncRunId || undefined,
          additional_context: additionalContext || undefined,
        });
        toast.success("Draft generated!", {
          description: `${PLATFORM_LABELS[platform]} draft created.`,
        });
        onOpenChange(false);
        if (onGenerated) {
          onGenerated(result.draft_id);
        } else {
          router.push(`/projects/${projectId}/drafts/${result.draft_id}`);
        }
      }
    } catch (err) {
      toast.error("Generation failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsGenerating(false);
    }
  }

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            Generate Draft
          </DialogTitle>
          <DialogDescription>
            AI-powered draft generation from your project data.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* Mode toggle */}
          <div className="flex rounded-md border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => setMode("standard")}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors",
                mode === "standard"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Zap className="w-3.5 h-3.5" />
              Standard
            </button>
            <button
              type="button"
              onClick={() => setMode("agentic")}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors",
                mode === "agentic"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Bot className="w-3.5 h-3.5" />
              Agentic (4 rounds)
            </button>
          </div>

          {mode === "agentic" && !isGenerating && (
            <div className="text-xs text-muted-foreground bg-secondary/40 rounded-md px-3 py-2 space-y-1">
              <p className="font-medium text-foreground/80">Multi-model pipeline:</p>
              <div className="grid grid-cols-3 gap-1">
                <span className="flex items-center gap-1"><Pen className="w-3 h-3 text-blue-400" /> Gemini Flash</span>
                <span className="flex items-center gap-1"><Eye className="w-3 h-3 text-green-400" /> GPT-4o</span>
                <span className="flex items-center gap-1"><Shield className="w-3 h-3 text-amber-400" /> Local scan</span>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <Label>Platform</Label>
            <Select value={platform} onValueChange={(v) => setPlatform(v as Platform)}>
              <SelectTrigger className="bg-secondary/40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLATFORMS.map((p) => (
                  <SelectItem key={p} value={p}>
                    {PLATFORM_LABELS[p]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {completedRuns.length > 0 && (
            <div className="space-y-2">
              <Label>Base on sync run (optional)</Label>
              <Select value={syncRunId} onValueChange={(v) => setSyncRunId(v ?? "")}>
                <SelectTrigger className="bg-secondary/40">
                  <SelectValue placeholder="Latest activity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Latest activity</SelectItem>
                  {completedRuns.map((run: SyncRun) => (
                    <SelectItem key={run.id} value={run.id}>
                      {new Date(run.triggered_at).toLocaleDateString()} — {run.commits_fetched} commits
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-2">
            <Label>Additional context (optional)</Label>
            <Textarea
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              placeholder="Any specific angle, event, or context to emphasize..."
              className="bg-secondary/40 resize-none"
              rows={2}
            />
          </div>

          {/* Agentic progress pipeline */}
          {isGenerating && mode === "agentic" && (
            <div className="rounded-lg border border-border bg-secondary/20 p-3 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-foreground/80">
                  Round {currentRound}/{maxRounds}
                </span>
                <span className="text-xs text-muted-foreground font-mono">
                  {formatTime(elapsedSeconds)}
                </span>
              </div>

              {/* Progress bar */}
              <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
                  style={{
                    width: `${Math.min(100, ((currentRound - 1) * 4 + currentStage + 1) / (maxRounds * 4) * 100)}%`,
                  }}
                />
              </div>

              {/* Stage indicators */}
              <div className="space-y-1.5">
                {PIPELINE_STAGES.slice(0, 4).map((stage, idx) => {
                  const isActive = idx === currentStage;
                  const isDone = idx < currentStage;
                  const Icon = stage.icon;
                  return (
                    <div
                      key={stage.id}
                      className={cn(
                        "flex items-center gap-2 py-1 px-2 rounded text-xs transition-all",
                        isActive && "bg-primary/10 text-foreground",
                        isDone && "text-muted-foreground",
                        !isActive && !isDone && "text-muted-foreground/40",
                      )}
                    >
                      {isDone ? (
                        <Check className="w-3.5 h-3.5 text-green-500 shrink-0" />
                      ) : isActive ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
                      ) : (
                        <Circle className="w-3.5 h-3.5 shrink-0 opacity-30" />
                      )}
                      <Icon className="w-3.5 h-3.5 shrink-0" />
                      <span className={cn("flex-1", isActive && "font-medium")}>{stage.label}</span>
                      {stage.model && (
                        <span className="text-[10px] text-muted-foreground">{stage.model}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Standard loading */}
          {isGenerating && mode === "standard" && (
            <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/30 px-3 py-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
              <span className="text-xs text-foreground/80">Generating with Gemini Flash...</span>
              <span className="text-xs text-muted-foreground font-mono ml-auto">
                {formatTime(elapsedSeconds)}
              </span>
            </div>
          )}

          <Button
            className="w-full gap-2"
            onClick={handleGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : mode === "agentic" ? (
              <Bot className="w-4 h-4" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {isGenerating
              ? mode === "agentic"
                ? "Running pipeline..."
                : "Generating..."
              : mode === "agentic"
              ? "Generate (4-round pipeline)"
              : "Generate Draft"}
          </Button>
        </div>

        {/* Trace after completion */}
        {loopTrace && loopTrace.length > 0 && !isGenerating && (
          <div className="border-t border-border pt-4 space-y-2">
            <button
              type="button"
              onClick={() => setTraceExpanded((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
            >
              {traceExpanded ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
              Pipeline Trace ({loopTrace.length} rounds)
            </button>

            {traceExpanded && (
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {loopTrace.map((step, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-border bg-secondary/20 px-3 py-2 space-y-1"
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs px-1.5 py-0">
                        R{step.round}
                      </Badge>
                      <span className="text-xs font-medium">
                        Score: {step.score}/10
                      </span>
                      {step.privacy_clean !== undefined && (
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[10px] px-1 py-0",
                            step.privacy_clean
                              ? "text-green-400 border-green-500/30"
                              : "text-red-400 border-red-500/30",
                          )}
                        >
                          <Shield className="w-2.5 h-2.5 mr-0.5" />
                          {step.privacy_clean ? "Clean" : "Flagged"}
                        </Badge>
                      )}
                      <span className="text-[10px] text-muted-foreground ml-auto">
                        {step.generator ?? ""} / {step.reviewer ?? ""}
                      </span>
                    </div>
                    {step.critique && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {step.critique.slice(0, 200)}...
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
