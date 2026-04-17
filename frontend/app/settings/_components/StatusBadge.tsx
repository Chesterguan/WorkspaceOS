"use client";

import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, XCircle, Info } from "lucide-react";

export type ConnectionStatus = "loading" | "connected" | "disconnected" | "manual";

export function StatusBadge({ status }: { status: ConnectionStatus }) {
  if (status === "loading") {
    return (
      <Badge variant="outline" className="gap-1.5 text-xs text-muted-foreground border-border">
        <Loader2 className="w-3 h-3 animate-spin" />
        Checking…
      </Badge>
    );
  }
  if (status === "connected") {
    return (
      <Badge className="gap-1.5 text-xs bg-green-900/40 text-green-400 border border-green-700/50 hover:bg-green-900/40">
        <CheckCircle2 className="w-3 h-3" />
        Connected
      </Badge>
    );
  }
  if (status === "disconnected") {
    return (
      <Badge variant="outline" className="gap-1.5 text-xs text-red-400 border-red-700/50">
        <XCircle className="w-3 h-3" />
        Disconnected
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1.5 text-xs text-muted-foreground border-border">
      <Info className="w-3 h-3" />
      Manual only
    </Badge>
  );
}
