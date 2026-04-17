"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { linkedin as linkedinApi } from "@/lib/api";
import { Loader2, Link as LinkIcon, XCircle } from "lucide-react";
import { StatusBadge, type ConnectionStatus } from "./StatusBadge";

export function LinkedInCard() {
  const [status, setStatus] = useState<ConnectionStatus>("loading");
  const [linkedInName, setLinkedInName] = useState<string | undefined>();
  const [isActing, setIsActing] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await linkedinApi.getStatus();
      setStatus(res.connected ? "connected" : "disconnected");
      setLinkedInName(res.name);
    } catch {
      setStatus("disconnected");
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  async function handleConnect() {
    setIsActing(true);
    try {
      const { url } = await linkedinApi.getAuthUrl();
      const popup = window.open(url, "linkedin-oauth", "width=600,height=700,noopener");
      const poll = setInterval(async () => {
        if (!popup || popup.closed) {
          clearInterval(poll);
          await fetchStatus();
          setIsActing(false);
        }
      }, 800);
    } catch (err) {
      toast.error("Failed to start LinkedIn OAuth", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      setIsActing(false);
    }
  }

  async function handleDisconnect() {
    setIsActing(true);
    try {
      await linkedinApi.disconnect();
      setStatus("disconnected");
      setLinkedInName(undefined);
      toast.success("LinkedIn disconnected");
    } catch (err) {
      toast.error("Failed to disconnect LinkedIn", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsActing(false);
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-700 flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 24 24" fill="white" className="w-5 h-5">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
              </svg>
            </div>
            <div>
              <CardTitle className="text-base">LinkedIn</CardTitle>
              {linkedInName && status === "connected" && (
                <p className="text-xs text-muted-foreground mt-0.5">{linkedInName}</p>
              )}
            </div>
          </div>
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm text-muted-foreground">
          Connect to publish drafts directly to your LinkedIn profile from the draft editor.
        </CardDescription>
        <div className="flex gap-2">
          {status === "loading" && (
            <Button variant="outline" size="sm" disabled className="gap-1.5">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Loading…
            </Button>
          )}
          {status === "disconnected" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleConnect}
              disabled={isActing}
              className="gap-1.5 border-blue-600/50 text-blue-400 hover:bg-blue-950/30"
            >
              {isActing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <LinkIcon className="w-3.5 h-3.5" />}
              {isActing ? "Connecting…" : "Connect LinkedIn"}
            </Button>
          )}
          {status === "connected" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDisconnect}
              disabled={isActing}
              className="gap-1.5 border-destructive/40 text-destructive hover:bg-destructive/10"
            >
              {isActing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
              {isActing ? "Disconnecting…" : "Disconnect"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
