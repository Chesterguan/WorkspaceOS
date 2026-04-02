"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { linkedin as linkedinApi, github_status as githubStatusApi } from "@/lib/api";
import { toast } from "sonner";
import {
  ArrowLeft,
  Loader2,
  Link as LinkIcon,
  GitFork,
  CheckCircle2,
  XCircle,
  Info,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

type ConnectionStatus = "loading" | "connected" | "disconnected" | "manual";

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ConnectionStatus }) {
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
  // manual
  return (
    <Badge variant="outline" className="gap-1.5 text-xs text-muted-foreground border-border">
      <Info className="w-3 h-3" />
      Manual only
    </Badge>
  );
}

// ─── LinkedIn Card ────────────────────────────────────────────────────────────

function LinkedInCard() {
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
            {/* LinkedIn "in" wordmark icon using SVG */}
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
              {isActing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <LinkIcon className="w-3.5 h-3.5" />
              )}
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
              {isActing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <XCircle className="w-3.5 h-3.5" />
              )}
              {isActing ? "Disconnecting…" : "Disconnect"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── GitHub Card ──────────────────────────────────────────────────────────────

function GitHubCard() {
  const [status, setStatus] = useState<ConnectionStatus>("loading");
  const [username, setUsername] = useState<string>("");

  useEffect(() => {
    githubStatusApi.check().then((res) => {
      setStatus(res.connected ? "connected" : "disconnected");
      setUsername(res.username);
    }).catch(() => {
      setStatus("disconnected");
    });
  }, []);

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0">
              <GitFork className="w-5 h-5 text-foreground" />
            </div>
            <div>
              <CardTitle className="text-base">GitHub</CardTitle>
              {username && status === "connected" && (
                <p className="text-xs text-muted-foreground mt-0.5">@{username}</p>
              )}
            </div>
          </div>
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm text-muted-foreground">
          Connected via <code className="text-xs bg-secondary/60 px-1 py-0.5 rounded">GITHUB_TOKEN</code> environment
          variable. Used to sync commits, create GitHub Releases, and import repos.
        </CardDescription>
        <p className="text-xs text-muted-foreground">
          To change accounts, update <code className="bg-secondary/60 px-1 py-0.5 rounded">GITHUB_TOKEN</code> in your
          environment and restart the server.
        </p>
      </CardContent>
    </Card>
  );
}

// ─── Static manual-only platform card ────────────────────────────────────────

interface ManualPlatformCardProps {
  icon: React.ReactNode;
  name: string;
  reason: string;
  description: string;
}

function ManualPlatformCard({ icon, name, reason, description }: ManualPlatformCardProps) {
  return (
    <Card className="bg-card border-border opacity-75">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0">
              {icon}
            </div>
            <CardTitle className="text-base">{name}</CardTitle>
          </div>
          <StatusBadge status="manual" />
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5">
        <p className="text-sm font-medium text-muted-foreground">{reason}</p>
        <CardDescription className="text-sm text-muted-foreground">{description}</CardDescription>
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="border-b border-border px-8 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/projects">
              <Button variant="ghost" size="icon" className="w-8 h-8 text-muted-foreground hover:text-foreground">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                Platform connections and global configuration
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-8 py-8 space-y-8">
        {/* Platform Connections section */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Platform Connections</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Configure once here — connected platforms are available across all projects.
            </p>
          </div>
          <Separator className="bg-border" />

          {/* Connected platforms */}
          <div className="grid gap-4">
            <LinkedInCard />
            <GitHubCard />
          </div>

          {/* Manual-only platforms */}
          <div className="space-y-2 pt-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Manual publishing only
            </p>
            <div className="grid gap-3">
              <ManualPlatformCard
                icon={
                  // X / Twitter — no official lucide icon; use a clean SVG
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-foreground">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L1.254 2.25H8.08l4.259 5.631ZM17.083 20.13h1.832L7.084 4.126H5.117Z" />
                  </svg>
                }
                name="Twitter / X"
                reason="Manual only — API requires paid tier"
                description="The Twitter/X API v2 write access requires a paid developer plan. Copy your draft and post it manually, then mark it as posted."
              />
              <ManualPlatformCard
                icon={
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-foreground">
                    <path d="M13.54 12a6.8 6.8 0 01-6.77 6.82A6.8 6.8 0 010 12a6.8 6.8 0 016.77-6.82A6.8 6.8 0 0113.54 12zM20.96 12c0 3.54-1.51 6.42-3.38 6.42-1.87 0-3.39-2.88-3.39-6.42s1.52-6.42 3.39-6.42 3.38 2.88 3.38 6.42M24 12c0 3.17-.53 5.75-1.19 5.75-.66 0-1.19-2.58-1.19-5.75s.53-5.75 1.19-5.75C23.47 6.25 24 8.83 24 12z" />
                  </svg>
                }
                name="Medium"
                reason="Manual only — API closed January 2025"
                description="Medium deprecated and closed their public API in January 2025. Copy your draft and publish it via the Medium editor."
              />
              <ManualPlatformCard
                icon={
                  // Xiaohongshu / Little Red Book — generic bookmark icon proxy
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-red-400">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z" />
                  </svg>
                }
                name="Xiaohongshu (小红书)"
                reason="Manual only — no public API"
                description="Xiaohongshu does not provide a public posting API. Copy your draft and post it manually via the app or web editor."
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
