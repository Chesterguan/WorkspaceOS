"use client";

import { Badge } from "@/components/ui/badge";
import { Bot } from "lucide-react";
import type { AgentLogEntry } from "@/lib/types";

interface AgentLogPanelProps {
  entries: AgentLogEntry[];
}

export function AgentLogPanel({ entries }: AgentLogPanelProps) {
  if (entries.length === 0) return null;

  return (
    <details className="mb-4 border rounded-lg">
      <summary className="p-3 cursor-pointer flex items-center gap-2 font-medium text-sm hover:bg-secondary/30 rounded-lg transition-colors">
        <Bot className="h-4 w-4 text-violet-400" /> Agent Log ({entries.length} actions)
      </summary>
      <div className="p-3 max-h-80 overflow-y-auto space-y-1 border-t">
        {entries.map((entry, i) => (
          <div key={i} className="flex items-start gap-2 text-xs font-mono py-0.5">
            <Badge variant="outline" className="shrink-0 text-[10px]">
              {entry.agent.replace("gemini_", "").replace("openai_", "").replace("ollama_", "").replace("reviewer_", "")}
            </Badge>
            <span className="text-muted-foreground">{entry.action}</span>
            {entry.section && <span className="text-violet-400">[{entry.section}]</span>}
            {entry.score !== null && (
              <Badge variant={entry.score >= 8 ? "default" : "destructive"} className="text-[10px]">
                {entry.score}/10
              </Badge>
            )}
            <span className="truncate text-muted-foreground/70">{entry.detail}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
