"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { appSettings } from "@/lib/api";
import type { UsageStats } from "@/lib/types";
import { BarChart3, Loader2 } from "lucide-react";

export function UsageCard() {
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    appSettings
      .getUsage()
      .then(setUsage)
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="p-6 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading usage...
        </CardContent>
      </Card>
    );
  }

  if (!usage) return null;

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/15 flex items-center justify-center flex-shrink-0">
            <BarChart3 className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <CardTitle className="text-base">AI Usage & Costs</CardTitle>
            <CardDescription className="text-xs mt-0.5">
              Estimated costs based on token usage. Actual costs may vary.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Today", data: usage.today },
            { label: "This Week", data: usage.this_week },
            { label: "This Month", data: usage.this_month },
          ].map(({ label, data }) => (
            <div key={label} className="rounded-lg border border-border p-3 text-center">
              <p className="text-lg font-bold">${data.estimated_cost_usd.toFixed(2)}</p>
              <p className="text-[11px] text-muted-foreground">{label}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{data.calls} calls</p>
            </div>
          ))}
        </div>
        {Object.keys(usage.by_provider).length > 0 && (
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {Object.entries(usage.by_provider).map(([provider, stats]) => (
              <span key={provider}>
                {provider}: ${stats.cost.toFixed(2)} ({stats.calls} calls)
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
