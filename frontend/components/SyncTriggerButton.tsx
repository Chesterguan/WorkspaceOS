"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { sync } from "@/lib/api";
import { toast } from "sonner";

interface SyncTriggerButtonProps {
  projectId: string;
  onSyncStarted?: () => void;
  variant?: "default" | "outline" | "secondary";
  size?: "default" | "sm" | "lg";
}

export function SyncTriggerButton({
  projectId,
  onSyncStarted,
  variant = "default",
  size = "default",
}: SyncTriggerButtonProps) {
  const [isSyncing, setIsSyncing] = useState(false);

  async function handleSync() {
    setIsSyncing(true);
    try {
      await sync.trigger(projectId);
      toast.success("Sync started", {
        description: "GitHub activity is being fetched. This may take a moment.",
      });
      onSyncStarted?.();
    } catch (err) {
      toast.error("Sync failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleSync}
      disabled={isSyncing}
    >
      <RefreshCw className={`w-4 h-4 mr-2 ${isSyncing ? "animate-spin" : ""}`} />
      {isSyncing ? "Syncing..." : "Sync Now"}
    </Button>
  );
}
