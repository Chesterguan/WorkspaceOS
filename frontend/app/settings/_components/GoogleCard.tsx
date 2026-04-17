"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { google as googleApi, skills as skillsApi } from "@/lib/api";
import { Loader2, Link as LinkIcon, CalendarDays, XCircle } from "lucide-react";
import { StatusBadge, type ConnectionStatus } from "./StatusBadge";

// Connects the user's Google account (Calendar read-only for v1; Gmail
// to follow). Once connected, a "Sync Calendar" button lets the user
// ingest the last 7 days + next 14 days of primary-calendar events.
// Each event gets AI-classified into one of the user's projects;
// anything below the confidence threshold lands in the auto-created
// Inbox project.

export function GoogleCard() {
  const [status, setStatus] = useState<ConnectionStatus>("loading");
  const [isActing, setIsActing] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await googleApi.getStatus();
      setStatus(res.connected ? "connected" : "disconnected");
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
      const { url } = await googleApi.getAuthUrl();
      const popup = window.open(url, "google-oauth", "width=600,height=700,noopener");
      const poll = setInterval(async () => {
        if (!popup || popup.closed) {
          clearInterval(poll);
          await fetchStatus();
          setIsActing(false);
        }
      }, 800);
    } catch (err) {
      toast.error("Failed to start Google OAuth", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      setIsActing(false);
    }
  }

  async function handleDisconnect() {
    setIsActing(true);
    try {
      await googleApi.disconnect();
      setStatus("disconnected");
      toast.success("Google disconnected");
    } catch (err) {
      toast.error("Failed to disconnect Google", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsActing(false);
    }
  }

  async function handleSyncCalendar() {
    setIsSyncing(true);
    try {
      const result = await skillsApi.syncCalendar();
      toast.success(
        `Synced ${result.created} new event${result.created === 1 ? "" : "s"}`,
        {
          description:
            `${result.fetched} fetched · ${result.skipped} already ingested · ` +
            `${result.inbox} routed to Inbox`,
        },
      );
    } catch (err) {
      toast.error("Calendar sync failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 48 48" className="w-5 h-5">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
              </svg>
            </div>
            <div>
              <CardTitle className="text-base">Google</CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                Calendar ingestion · read-only
              </p>
            </div>
          </div>
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm text-muted-foreground">
          Pull recent calendar events into project memory. Each event is
          AI-classified to the most likely project; low-confidence items
          land in an auto-created Inbox project you can re-tag later.
        </CardDescription>
        <div className="flex flex-wrap gap-2">
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
              className="gap-1.5"
            >
              {isActing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <LinkIcon className="w-3.5 h-3.5" />}
              {isActing ? "Connecting…" : "Connect Google"}
            </Button>
          )}
          {status === "connected" && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSyncCalendar}
                disabled={isSyncing}
                className="gap-1.5"
              >
                {isSyncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CalendarDays className="w-3.5 h-3.5" />}
                {isSyncing ? "Syncing…" : "Sync Calendar"}
              </Button>
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
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
