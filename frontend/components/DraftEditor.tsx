"use client";

import { Textarea } from "@/components/ui/textarea";
import { platformCharLimit } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { Platform } from "@/lib/types";

interface DraftEditorProps {
  content: string;
  platform: Platform;
  onChange: (value: string) => void;
}

export function DraftEditor({ content, platform, onChange }: DraftEditorProps) {
  const limit = platformCharLimit(platform);
  const count = content.length;
  const overLimit = limit !== null && count > limit;
  const nearLimit = limit !== null && count > limit * 0.9 && !overLimit;

  return (
    <div className="flex flex-col gap-2 h-full">
      <Textarea
        value={content}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "flex-1 min-h-[400px] resize-none bg-secondary/30 text-base leading-relaxed font-mono text-sm",
          overLimit && "border-destructive focus-visible:ring-destructive",
        )}
        placeholder="Start writing your draft..."
      />
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">
          {limit !== null
            ? `Character limit: ${limit}`
            : "No character limit"}
        </span>
        <span
          className={cn(
            "tabular-nums",
            overLimit
              ? "text-destructive font-medium"
              : nearLimit
                ? "text-yellow-400"
                : "text-muted-foreground",
          )}
        >
          {count}
          {limit !== null && ` / ${limit}`}
        </span>
      </div>
    </div>
  );
}
