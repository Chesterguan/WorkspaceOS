"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sparkles } from "lucide-react";

interface EvolutionSummaryCardProps {
  summary: string;
}

export function EvolutionSummaryCard({ summary }: EvolutionSummaryCardProps) {
  return (
    <Card className="border-primary/20 bg-primary/5">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2 text-primary">
          <Sparkles className="w-4 h-4" />
          Latest Evolution Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap">
          {summary}
        </p>
      </CardContent>
    </Card>
  );
}
