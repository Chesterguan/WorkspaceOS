"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { microsoft as microsoftApi, skills as skillsApi } from "@/lib/api";
import {
  Loader2,
  Link as LinkIcon,
  CalendarDays,
  Mail,
  XCircle,
} from "lucide-react";
import { StatusBadge, type ConnectionStatus } from "./StatusBadge";

// One OAuth, two skills (Outlook Calendar + Outlook Mail). Same token
// covers both; the individual sync buttons trigger the per-source skill
// endpoints. Teams chat is a follow-up — not wired here yet.

export function MicrosoftCard() {
  const [status, setStatus] = useState<ConnectionStatus>("loading");
  const [isActing, setIsActing] = useState(false);
  const [syncingCal, setSyncingCal] = useState(false);
  const [syncingMail, setSyncingMail] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await microsoftApi.getStatus();
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
      const { url } = await microsoftApi.getAuthUrl();
      const popup = window.open(url, "microsoft-oauth", "width=600,height=700,noopener");
      const poll = setInterval(async () => {
        if (!popup || popup.closed) {
          clearInterval(poll);
          await fetchStatus();
          setIsActing(false);
        }
      }, 800);
    } catch (err) {
      toast.error("Failed to start Microsoft OAuth", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      setIsActing(false);
    }
  }

  async function handleDisconnect() {
    setIsActing(true);
    try {
      await microsoftApi.disconnect();
      setStatus("disconnected");
      toast.success("Microsoft disconnected");
    } catch (err) {
      toast.error("Failed to disconnect Microsoft", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsActing(false);
    }
  }

  async function handleSyncCalendar() {
    setSyncingCal(true);
    try {
      const result = await skillsApi.syncOutlookCalendar();
      toast.success(
        `Synced ${result.created} new event${result.created === 1 ? "" : "s"}`,
        {
          description:
            `${result.fetched} fetched · ${result.skipped} already ingested · ` +
            `${result.inbox} routed to Inbox`,
        },
      );
    } catch (err) {
      toast.error("Outlook Calendar sync failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSyncingCal(false);
    }
  }

  async function handleSyncMail() {
    setSyncingMail(true);
    try {
      const result = await skillsApi.syncOutlookMail();
      toast.success(
        `Synced ${result.created} new email${result.created === 1 ? "" : "s"}`,
        {
          description:
            `${result.fetched} fetched · ${result.skipped} already ingested · ` +
            `${result.inbox} routed to Inbox`,
        },
      );
    } catch (err) {
      toast.error("Outlook Mail sync failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSyncingMail(false);
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 23 23" className="w-5 h-5">
                <rect x="1" y="1" width="10" height="10" fill="#F25022" />
                <rect x="12" y="1" width="10" height="10" fill="#7FBA00" />
                <rect x="1" y="12" width="10" height="10" fill="#00A4EF" />
                <rect x="12" y="12" width="10" height="10" fill="#FFB900" />
              </svg>
            </div>
            <div>
              <CardTitle className="text-base">Microsoft</CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                Outlook Calendar + Mail · read-only
              </p>
            </div>
          </div>
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm text-muted-foreground">
          Pull recent Outlook calendar events and Inbox messages into
          project memory. Each item is AI-classified to a project;
          low-confidence items land in the auto-created Inbox project.
          Teams chat support is coming next.
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
              {isActing ? "Connecting…" : "Connect Microsoft"}
            </Button>
          )}
          {status === "connected" && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSyncCalendar}
                disabled={syncingCal}
                className="gap-1.5"
              >
                {syncingCal ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CalendarDays className="w-3.5 h-3.5" />}
                {syncingCal ? "Syncing…" : "Sync Calendar"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSyncMail}
                disabled={syncingMail}
                className="gap-1.5"
              >
                {syncingMail ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mail className="w-3.5 h-3.5" />}
                {syncingMail ? "Syncing…" : "Sync Mail"}
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
