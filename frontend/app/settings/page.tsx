"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  linkedin as linkedinApi,
  github_status as githubStatusApi,
  appSettings,
  google as googleApi,
  skills as skillsApi,
} from "@/lib/api";
import { toast } from "sonner";
import {
  ArrowLeft,
  Loader2,
  Link as LinkIcon,
  GitFork,
  CheckCircle2,
  XCircle,
  Info,
  Key,
  Pencil,
  Trash2,
  BarChart3,
  Shield,
  CalendarDays,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { KeyStatus, UsageStats } from "@/lib/types";

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

// ─── Google Card ──────────────────────────────────────────────────────────────
//
// Connects the user's Google account (Calendar read-only for v1; Gmail to
// follow). Once connected, a "Sync Calendar" button lets the user ingest
// the last 7 days + next 14 days of primary-calendar events. Each event
// gets AI-classified into one of the user's projects; anything below the
// confidence threshold lands in the auto-created Inbox project.

function GoogleCard() {
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
              {/* Google "G" SVG */}
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
              {isActing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <LinkIcon className="w-3.5 h-3.5" />
              )}
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
                {isSyncing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <CalendarDays className="w-3.5 h-3.5" />
                )}
                {isSyncing ? "Syncing…" : "Sync Calendar"}
              </Button>
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
            </>
          )}
        </div>
      </CardContent>
    </Card>
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

// ─── API Keys Card ───────────────────────────────────────────────────────────

const KEY_LABELS: Record<string, { label: string; placeholder: string }> = {
  gemini_api_key: { label: "Google Gemini", placeholder: "AIza..." },
  openai_api_key: { label: "OpenAI", placeholder: "sk-..." },
  anthropic_api_key: { label: "Anthropic", placeholder: "sk-ant-..." },
  github_token: { label: "GitHub Token", placeholder: "ghp_..." },
  api_secret_key: { label: "API Secret Key", placeholder: "your-secret-key" },
  linkedin_client_id: { label: "LinkedIn Client ID", placeholder: "client-id" },
  linkedin_client_secret: { label: "LinkedIn Client Secret", placeholder: "client-secret" },
  devto_api_key: { label: "Dev.to API Key", placeholder: "your-devto-api-key" },
  hashnode_api_key: { label: "Hashnode API Key", placeholder: "your-hashnode-pat" },
  hashnode_publication_id: { label: "Hashnode Publication ID", placeholder: "publication-id" },
  google_drive_credentials: { label: "Google Drive", placeholder: "OAuth credentials JSON" },
  notion_api_key: { label: "Notion API Key", placeholder: "secret_..." },
};

function ApiKeysCard() {
  const [keys, setKeys] = useState<KeyStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    try {
      const res = await appSettings.getKeys();
      setKeys(res.keys);
    } catch {
      toast.error("Failed to load API key status");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  async function handleSave(key: string) {
    const value = editValues[key];
    if (!value?.trim()) return;
    setIsSaving(true);
    try {
      await appSettings.setKeys({ keys: { [key]: value.trim() } });
      toast.success(`${KEY_LABELS[key]?.label || key} updated`);
      setEditingKey(null);
      setEditValues((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      await fetchKeys();
    } catch {
      toast.error("Failed to save key");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(key: string) {
    try {
      await appSettings.deleteKey(key);
      toast.success(`${KEY_LABELS[key]?.label || key} removed from DB (using .env fallback)`);
      setEditingKey(null);
      await fetchKeys();
    } catch {
      toast.error("Failed to remove key");
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-violet-500/15 flex items-center justify-center flex-shrink-0">
              <Key className="w-5 h-5 text-violet-400" />
            </div>
            <div>
              <CardTitle className="text-base">AI & API Keys</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Manage API keys for AI providers and integrations. Stored encrypted in the database.
              </CardDescription>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading key status…
          </div>
        ) : (
          <div className="space-y-2">
            {keys.map((k) => {
              const meta = KEY_LABELS[k.key] || { label: k.key, placeholder: "" };
              const isEditing = editingKey === k.key;

              return (
                <div key={k.key} className="flex items-center gap-3 py-2 border-b border-border/50 last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{meta.label}</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px]",
                          k.source === "db"
                            ? "text-violet-400 border-violet-500/30"
                            : k.masked_value !== "Not set"
                              ? "text-muted-foreground border-border"
                              : "text-red-400 border-red-500/30",
                        )}
                      >
                        {k.source === "db" ? "DB" : k.masked_value !== "Not set" ? "ENV" : "Missing"}
                      </Badge>
                    </div>
                    {isEditing ? (
                      <div className="flex items-center gap-2 mt-1.5">
                        <input
                          type="password"
                          value={editValues[k.key] || ""}
                          onChange={(e) => setEditValues((prev) => ({ ...prev, [k.key]: e.target.value }))}
                          placeholder={meta.placeholder}
                          className="flex-1 h-8 px-2 text-xs bg-secondary/50 border border-border rounded focus:outline-none focus:ring-1 focus:ring-violet-500/50 font-mono"
                          autoFocus
                        />
                        <Button
                          size="sm"
                          variant="default"
                          className="h-7 text-xs"
                          onClick={() => handleSave(k.key)}
                          disabled={isSaving || !editValues[k.key]?.trim()}
                        >
                          {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : "Save"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={() => {
                            setEditingKey(null);
                            setEditValues((prev) => {
                              const next = { ...prev };
                              delete next[k.key];
                              return next;
                            });
                          }}
                        >
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">
                        {k.masked_value}
                      </p>
                    )}
                  </div>
                  {!isEditing && (
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                        onClick={() => setEditingKey(k.key)}
                        title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      {k.source === "db" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          onClick={() => handleDelete(k.key)}
                          title="Remove from DB (use .env fallback)"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Usage Card ──────────────────────────────────────────────────────────────

function UsageCard() {
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    appSettings.getUsage()
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

// ─── Backup Card ────────────────────────────────────────────────────────────

function BackupCard() {
  const [backups, setBackups] = useState<Array<{ filename: string; size_human: string; created_at: string }>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isBacking, setIsBacking] = useState(false);

  const fetchBackups = useCallback(async () => {
    try {
      const res = await appSettings.listBackups();
      setBackups(res.backups);
    } catch {}
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { fetchBackups(); }, [fetchBackups]);

  async function handleBackup() {
    setIsBacking(true);
    try {
      const res = await appSettings.triggerBackup();
      if (res.success) {
        toast.success(res.message || "Backup complete");
        await fetchBackups();
      } else {
        toast.error("Backup failed", { description: res.error });
      }
    } catch { toast.error("Backup failed"); }
    finally { setIsBacking(false); }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-500/15 flex items-center justify-center flex-shrink-0">
              <Shield className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <CardTitle className="text-base">Database Backups</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Automatic daily backups. Stored in the Docker volume.
              </CardDescription>
            </div>
          </div>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={handleBackup} disabled={isBacking}>
            {isBacking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Shield className="w-3.5 h-3.5" />}
            Backup Now
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : backups.length === 0 ? (
          <p className="text-xs text-muted-foreground">No backups yet. Click &quot;Backup Now&quot; to create one.</p>
        ) : (
          <div className="space-y-1">
            {backups.slice(0, 5).map((b) => (
              <div key={b.filename} className="flex items-center justify-between text-xs py-1">
                <span className="font-mono text-muted-foreground">{b.filename}</span>
                <span className="text-muted-foreground">{b.size_human}</span>
              </div>
            ))}
          </div>
        )}
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
        {/* AI & API Keys section */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground">AI & API Keys</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Keys are encrypted and stored in the database. DB values override .env defaults.
            </p>
          </div>
          <Separator className="bg-border" />
          <ApiKeysCard />
          <UsageCard />
          <BackupCard />
        </section>

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
            <GoogleCard />
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
