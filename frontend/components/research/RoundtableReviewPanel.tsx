"use client";

import Image from "next/image";
import { Badge } from "@/components/ui/badge";
import { Users } from "lucide-react";
import type { ReviewerFeedback } from "@/lib/types";

interface RoundtableReviewPanelProps {
  reviews: ReviewerFeedback[];
}

export function RoundtableReviewPanel({ reviews }: RoundtableReviewPanelProps) {
  if (reviews.length === 0) return null;

  const avgScore = (reviews.reduce((s, r) => s + r.score, 0) / reviews.length).toFixed(1);

  return (
    <details className="mb-4 border rounded-lg" open>
      <summary className="p-3 cursor-pointer flex items-center gap-2 font-medium text-sm hover:bg-secondary/30 rounded-lg transition-colors">
        <Users className="h-4 w-4 text-violet-400" />
        Panel Review ({reviews.length} reviewers, avg {avgScore}/10)
      </summary>
      <div className="p-3 space-y-3 border-t">
        {reviews.map((r) => (
          <div
            key={r.reviewer_id}
            className="border rounded-lg p-3 space-y-2"
            style={r.color ? { borderLeftWidth: "3px", borderLeftColor: r.color } : undefined}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {r.avatar && (
                  <Image
                    src={r.avatar}
                    alt={r.reviewer_name}
                    width={28}
                    height={28}
                    className="rounded-full border"
                    style={{ borderColor: r.color || "var(--border)" }}
                  />
                )}
                <div>
                  <span className="text-sm font-semibold" style={r.color ? { color: r.color } : undefined}>
                    {r.reviewer_name}
                  </span>
                  <span className="text-xs text-muted-foreground ml-2">({r.modeled_after})</span>
                </div>
              </div>
              <Badge
                variant={r.score >= 8 ? "default" : r.score >= 7 ? "outline" : "destructive"}
                className="text-xs"
              >
                {r.score}/10
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground">{r.focus}</p>
            {r.critical_issues.length > 0 && (
              <div>
                <p className="text-[11px] font-semibold text-red-400">Critical Issues:</p>
                <ul className="text-xs text-muted-foreground list-disc list-inside">
                  {r.critical_issues.map((ci, i) => <li key={i}>{ci}</li>)}
                </ul>
              </div>
            )}
            {r.strengths.length > 0 && (
              <div>
                <p className="text-[11px] font-semibold text-green-400">Strengths:</p>
                <ul className="text-xs text-muted-foreground list-disc list-inside">
                  {r.strengths.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
            {r.suggestions.length > 0 && (
              <div>
                <p className="text-[11px] font-semibold text-amber-400">Suggestions:</p>
                <ul className="text-xs text-muted-foreground list-disc list-inside">
                  {r.suggestions.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
