"use client";

// API keys settings card. Designed for non-developers: every key has
// a plain-language ⓘ popover with step-by-step instructions, and a
// "smart paste" box at the top auto-routes pasted keys to the right
// slot by detecting their prefix (so users don't have to figure out
// which row matches their key).
//
// Three semantic groups: AI Provider / Publishing / Integrations.
// `api_secret_key` is intentionally hidden — it's internal HTTP auth,
// not a user-facing third-party credential.

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { appSettings } from "@/lib/api";
import type { KeyStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ExternalLink,
  HelpCircle,
  Key,
  Loader2,
  Pencil,
  Sparkles,
  Trash2,
} from "lucide-react";

type KeyGroup = "ai" | "publishing" | "integration";

interface KeyMeta {
  label: string;
  placeholder: string;
  group: KeyGroup;
  getUrl: string;
  // Plain-language summary of what this key unlocks (for non-CS users).
  what: string;
  // Step-by-step setup instructions. Rendered as an ordered list in the
  // help popover. Keep each step short and action-oriented.
  steps: string[];
}

const KEY_META: Record<string, KeyMeta> = {
  gemini_api_key: {
    label: "Google Gemini",
    placeholder: "AIza...",
    group: "ai",
    getUrl: "https://aistudio.google.com/app/apikey",
    what: "Google's AI. Has a generous free tier — best default if you're just getting started.",
    steps: [
      "Sign in to Google AI Studio (link above).",
      'Click "Create API Key" (top-right).',
      "Pick or create a Google Cloud project.",
      "Copy the key (starts with AIza...).",
      "Paste it here and Save.",
    ],
  },
  openai_api_key: {
    label: "OpenAI",
    placeholder: "sk-...",
    group: "ai",
    getUrl: "https://platform.openai.com/api-keys",
    what: "Maker of ChatGPT and the GPT-4 family. Paid — no free tier for API.",
    steps: [
      "Sign in at platform.openai.com.",
      'API keys → "Create new secret key".',
      'Give it a name (e.g. "WorkspaceOS").',
      "Copy immediately — OpenAI only shows the key once.",
      "Paste it here and Save.",
    ],
  },
  anthropic_api_key: {
    label: "Anthropic",
    placeholder: "sk-ant-...",
    group: "ai",
    getUrl: "https://console.anthropic.com/settings/keys",
    what: "Maker of Claude. Paid — add credits at console.anthropic.com/settings/billing.",
    steps: [
      "Sign in at console.anthropic.com.",
      'Settings → API Keys → "Create Key".',
      "Copy the key (starts with sk-ant-...).",
      "Paste it here and Save.",
    ],
  },

  linkedin_client_id: {
    label: "LinkedIn — Client ID",
    placeholder: "client-id",
    group: "publishing",
    getUrl: "https://www.linkedin.com/developers/apps",
    what: "Half of the LinkedIn app credentials (the public half). Used to auto-publish posts to LinkedIn once that's wired up.",
    steps: [
      "Go to LinkedIn Developers → Apps (link above).",
      'Click "Create app" if you don\'t already have one.',
      "Open your app → Auth tab.",
      'Copy "Client ID" and paste it here.',
      'Also copy "Client Secret" — paste it in the row below.',
    ],
  },
  linkedin_client_secret: {
    label: "LinkedIn — Client Secret",
    placeholder: "client-secret",
    group: "publishing",
    getUrl: "https://www.linkedin.com/developers/apps",
    what: "The private half of the LinkedIn app credentials. Treat like a password.",
    steps: [
      "On the same LinkedIn app → Auth tab.",
      'Copy "Client Secret" (the private value).',
      "Paste it here and Save.",
    ],
  },
  devto_api_key: {
    label: "Dev.to",
    placeholder: "your-devto-api-key",
    group: "publishing",
    getUrl: "https://dev.to/settings/extensions",
    what: "Dev.to API key. Lets us auto-publish posts to your dev.to blog (when that feature lands).",
    steps: [
      "Sign in at dev.to and open Settings → Extensions.",
      'Scroll to "DEV Community API Keys".',
      "Generate a new key, copy it.",
      "Paste it here and Save.",
    ],
  },
  hashnode_api_key: {
    label: "Hashnode — API Key",
    placeholder: "your-hashnode-pat",
    group: "publishing",
    getUrl: "https://hashnode.com/settings/developer",
    what: "Hashnode Personal Access Token. Used to publish drafts to your Hashnode blog.",
    steps: [
      "Sign in at hashnode.com → Settings → Developer.",
      "Generate Personal Access Token.",
      "Copy and paste here.",
      "Then go grab your Publication ID (see row below).",
    ],
  },
  hashnode_publication_id: {
    label: "Hashnode — Publication ID",
    placeholder: "publication-id",
    group: "publishing",
    getUrl: "https://hashnode.com/settings/developer",
    what: "Identifies which Hashnode blog to post into (each blog has its own ID).",
    steps: [
      "On the same Hashnode Developer page.",
      'Find "Publication ID" of the blog you want to post to.',
      "Copy it and paste here.",
    ],
  },

  github_token: {
    label: "GitHub Token",
    placeholder: "ghp_... or github_pat_...",
    group: "integration",
    getUrl: "https://github.com/settings/personal-access-tokens/new",
    what: "Lets WorkspaceOS create GitHub issues — used by the in-app feedback button and any repo-write capabilities.",
    steps: [
      "Open the GitHub PAT page (link above).",
      'Resource owner: pick yourself. Expiration: 90 days is fine.',
      'Repository access: choose "Only select repositories" and pick the repo WorkspaceOS should file issues into.',
      'Scroll down to "Permissions" → "Repository permissions" (NOT Account permissions).',
      'Find "Issues" and set it to "Read and write".',
      'Click "Generate token", copy it, paste here and Save.',
    ],
  },
  google_drive_credentials: {
    label: "Google Drive",
    placeholder: "OAuth credentials JSON",
    group: "integration",
    getUrl: "https://console.cloud.google.com/apis/credentials",
    what: "Service account credentials JSON. Lets WorkspaceOS read files from your Google Drive folders.",
    steps: [
      "Open Google Cloud Console → Credentials.",
      'Create Credentials → "Service account".',
      "After creating, open the service account → Keys tab → Add Key → JSON.",
      "A .json file downloads. Open it in a text editor.",
      "Copy the entire JSON contents.",
      "Paste here and Save.",
    ],
  },
  notion_api_key: {
    label: "Notion API Key",
    placeholder: "secret_... or ntn_...",
    group: "integration",
    getUrl: "https://www.notion.so/profile/integrations",
    what: "Notion internal integration token. Lets WorkspaceOS ingest pages from your Notion workspace.",
    steps: [
      "Open notion.so/profile/integrations.",
      '"New integration" → name it WorkspaceOS, pick the workspace, type: "Internal".',
      'Capabilities: tick at least "Read content".',
      'Save → copy "Internal Integration Secret".',
      "Paste here and Save.",
      'IMPORTANT: in Notion, share each page you want to ingest with this integration ("•••" menu → "Connect to").',
    ],
  },
};

interface GroupMeta {
  id: KeyGroup;
  title: string;
  description: string;
}

const GROUPS: GroupMeta[] = [
  {
    id: "ai",
    title: "AI Provider",
    description:
      "Set the key for whichever provider you want to use. Gemini is the default for cloud generation; switch via CLOUD_AI_PROVIDER in .env. Want no cloud at all? Install Ollama (free, local) — README has model recommendations.",
  },
  {
    id: "publishing",
    title: "Publishing",
    description:
      "Auto-publish isn't wired up yet — keys are stored so it can be enabled later. For now, publishing is manual.",
  },
  {
    id: "integration",
    title: "Integrations",
    description: "Tokens for data-source and knowledge connectors.",
  },
];

// ── Smart paste prefix detection ──────────────────────────────────────
// Recognises the key formats with a stable, unambiguous prefix. Opaque
// keys (LinkedIn, Dev.to, Hashnode) don't match — the user picks from a
// dropdown after pasting.
function detectKeyType(raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  if (v.startsWith("AIza")) return "gemini_api_key";
  if (v.startsWith("sk-ant-")) return "anthropic_api_key";
  if (v.startsWith("sk-")) return "openai_api_key";
  if (v.startsWith("ghp_") || v.startsWith("github_pat_")) return "github_token";
  if (v.startsWith("secret_") || v.startsWith("ntn_")) return "notion_api_key";
  // Google Drive credentials JSON — heuristic: starts with { and
  // mentions one of the well-known credential shapes.
  if (
    v.startsWith("{") &&
    /"(type|installed|web)"\s*:\s*"?(service_account|oauth|web)?/i.test(v)
  ) {
    return "google_drive_credentials";
  }
  return null;
}

export function ApiKeysCard() {
  const [keys, setKeys] = useState<KeyStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);

  // Smart paste state — independent from per-row edit state.
  const [pasteValue, setPasteValue] = useState("");
  const [pasteTarget, setPasteTarget] = useState<string>("");
  const [pasteSaving, setPasteSaving] = useState(false);

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

  // Re-run prefix detection whenever the paste box changes. If the
  // user has manually picked a target, leave it alone (their pick wins
  // over auto-detection).
  useEffect(() => {
    if (!pasteValue.trim()) {
      setPasteTarget("");
      return;
    }
    const detected = detectKeyType(pasteValue);
    if (detected) setPasteTarget(detected);
  }, [pasteValue]);

  async function handleSave(key: string) {
    const value = editValues[key];
    if (!value?.trim()) return;
    setIsSaving(true);
    try {
      await appSettings.setKeys({ keys: { [key]: value.trim() } });
      toast.success(`${KEY_META[key]?.label || key} updated`);
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
      toast.success(`${KEY_META[key]?.label || key} removed from DB (using .env fallback)`);
      setEditingKey(null);
      await fetchKeys();
    } catch {
      toast.error("Failed to remove key");
    }
  }

  async function handlePasteSave() {
    if (!pasteTarget || !pasteValue.trim()) return;
    setPasteSaving(true);
    try {
      await appSettings.setKeys({ keys: { [pasteTarget]: pasteValue.trim() } });
      toast.success(`Saved as ${KEY_META[pasteTarget]?.label}`);
      setPasteValue("");
      setPasteTarget("");
      await fetchKeys();
    } catch {
      toast.error("Failed to save key");
    } finally {
      setPasteSaving(false);
    }
  }

  // Build group→rows partition. Skip any key without KEY_META so
  // api_secret_key stays hidden.
  const keyMap = new Map(keys.map((k) => [k.key, k]));
  const grouped: Record<KeyGroup, KeyStatus[]> = { ai: [], publishing: [], integration: [] };
  for (const [keyName, meta] of Object.entries(KEY_META)) {
    const status = keyMap.get(keyName);
    if (status) grouped[meta.group].push(status);
  }

  const detected = detectKeyType(pasteValue);
  const existingForTarget = pasteTarget ? keyMap.get(pasteTarget) : undefined;

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
                Saved keys are encrypted in the database and override any built-in defaults from <code>.env</code>.
                Click <strong>Help</strong> next to any key for step-by-step setup.
              </CardDescription>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Smart paste — paste any key, we'll route it. */}
        <SmartPaste
          value={pasteValue}
          onChange={setPasteValue}
          target={pasteTarget}
          onTargetChange={setPasteTarget}
          detected={detected}
          existing={existingForTarget}
          saving={pasteSaving}
          onSave={handlePasteSave}
        />

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading key status…
          </div>
        ) : (
          GROUPS.map((group) => {
            const rows = grouped[group.id];
            if (rows.length === 0) return null;
            return (
              <div key={group.id} className="space-y-2">
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {group.title}
                  </h3>
                  <p className="text-[11px] text-muted-foreground/80 mt-0.5">
                    {group.description}
                  </p>
                </div>
                <div className="space-y-1">
                  {rows.map((k) => (
                    <KeyRow
                      key={k.key}
                      status={k}
                      meta={KEY_META[k.key]}
                      isEditing={editingKey === k.key}
                      editValue={editValues[k.key] || ""}
                      isSaving={isSaving}
                      onEdit={() => setEditingKey(k.key)}
                      onChange={(v) => setEditValues((prev) => ({ ...prev, [k.key]: v }))}
                      onSave={() => handleSave(k.key)}
                      onCancel={() => {
                        setEditingKey(null);
                        setEditValues((prev) => {
                          const next = { ...prev };
                          delete next[k.key];
                          return next;
                        });
                      }}
                      onDelete={() => handleDelete(k.key)}
                    />
                  ))}
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

// ── Smart-paste subcomponent ─────────────────────────────────────────

interface SmartPasteProps {
  value: string;
  onChange: (v: string) => void;
  target: string;
  onTargetChange: (k: string) => void;
  detected: string | null;
  existing: KeyStatus | undefined;
  saving: boolean;
  onSave: () => void;
}

function SmartPaste({
  value,
  onChange,
  target,
  onTargetChange,
  detected,
  existing,
  saving,
  onSave,
}: SmartPasteProps) {
  // All known key names — used as the manual-pick dropdown when
  // detection fails (or when the user wants to override).
  const allKeys = Object.entries(KEY_META);

  return (
    <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-violet-400" />
        <span className="text-xs font-semibold text-violet-300">
          Paste a key — we&apos;ll figure out which slot it goes in
        </span>
      </div>
      <Input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Paste any API key here (sk-..., AIza..., ghp_..., {...})"
        className="bg-card/60 border-border h-9 text-sm font-mono"
        autoComplete="off"
        spellCheck={false}
        name={`smartpaste-${Math.random().toString(36).slice(2, 7)}`}
      />
      {value.trim() && (
        <div className="space-y-1.5">
          {/* Detection status — aria-live so screen readers announce
              the routing decision as the user pastes. */}
          <div role="status" aria-live="polite" className="text-[11px]">
            {detected ? (
              <span className="text-violet-300">
                Detected: <span className="font-semibold">{KEY_META[detected]?.label}</span>
              </span>
            ) : (
              <span className="text-muted-foreground">
                Couldn&apos;t auto-detect. Pick the slot manually:
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="text-[11px] text-muted-foreground" htmlFor="smartpaste-target">
              Save as:
            </label>
            <select
              id="smartpaste-target"
              value={target}
              onChange={(e) => onTargetChange(e.target.value)}
              className="h-7 text-xs bg-card/60 border border-border rounded px-2 focus:outline-none focus:ring-1 focus:ring-violet-500/50"
            >
              <option value="">— pick a slot —</option>
              {allKeys.map(([k, m]) => (
                <option key={k} value={k}>
                  {m.label}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              className="h-7 text-xs bg-violet-500 hover:bg-violet-600"
              onClick={onSave}
              disabled={saving || !target}
              title={target ? `Save into the ${KEY_META[target]?.label} slot` : "Pick a slot first"}
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : "Save"}
            </Button>
          </div>
          {existing && existing.masked_value !== "Not set" && (
            <span className="text-[10px] text-amber-400">
              Will replace existing value ({existing.masked_value})
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Per-key row with help popover ────────────────────────────────────

interface KeyRowProps {
  status: KeyStatus;
  meta: KeyMeta;
  isEditing: boolean;
  editValue: string;
  isSaving: boolean;
  onEdit: () => void;
  onChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
}

function KeyRow({
  status, meta, isEditing, editValue, isSaving,
  onEdit, onChange, onSave, onCancel, onDelete,
}: KeyRowProps) {
  const sourceLabel =
    status.source === "db" ? "Saved" : status.masked_value !== "Not set" ? "Default" : "Missing";
  const sourceClass =
    status.source === "db"
      ? "text-violet-400 border-violet-500/30"
      : status.masked_value !== "Not set"
        ? "text-muted-foreground border-border"
        : "text-red-400 border-red-500/30";

  return (
    <div className="flex items-center gap-3 py-2 border-b border-border/40 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{meta.label}</span>
          <Badge variant="outline" className={cn("text-[10px]", sourceClass)}>
            {sourceLabel}
          </Badge>
          <HelpPopover meta={meta} />
        </div>
        {isEditing ? (
          <div className="flex items-center gap-2 mt-1.5">
            <input
              type="password"
              value={editValue}
              onChange={(e) => onChange(e.target.value)}
              placeholder={meta.placeholder}
              className="flex-1 h-8 px-2 text-xs bg-secondary/50 border border-border rounded focus:outline-none focus:ring-1 focus:ring-violet-500/50 font-mono"
              autoFocus
            />
            <Button
              size="sm"
              variant="default"
              className="h-7 text-xs"
              onClick={onSave}
              disabled={isSaving || !editValue.trim()}
            >
              {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : "Save"}
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground font-mono mt-0.5">
            {status.masked_value}
          </p>
        )}
      </div>
      {!isEditing && (
        <div className="flex items-center gap-1 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
            onClick={onEdit}
            title="Edit"
          >
            <Pencil className="w-3.5 h-3.5" />
          </Button>
          {status.source === "db" && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
              onClick={onDelete}
              title="Remove from DB (use .env fallback)"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function HelpPopover({ meta }: { meta: KeyMeta }) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[11px] font-medium text-violet-400 hover:text-violet-300 transition-colors px-2 py-1 rounded-md border border-violet-500/30 hover:border-violet-500/60 bg-violet-500/5"
            title={`How to get ${meta.label}`}
            aria-label={`How to get ${meta.label}`}
          >
            <HelpCircle className="w-3 h-3" />
            Help
          </button>
        }
      />
      <PopoverContent
        align="start"
        side="bottom"
        className="w-80 p-3 text-xs space-y-2"
      >
        <div>
          <p className="text-sm font-semibold text-foreground">{meta.label}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">{meta.what}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground/80 mb-1">
            How to get it
          </p>
          <ol className="space-y-1 text-foreground/90 list-decimal pl-4">
            {meta.steps.map((step, i) => (
              <li key={i} className="text-[11px] leading-relaxed">{step}</li>
            ))}
          </ol>
        </div>
        <a
          href={meta.getUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-violet-400 hover:text-violet-300 font-medium pt-1"
        >
          Open key page
          <ExternalLink className="w-3 h-3" />
        </a>
      </PopoverContent>
    </Popover>
  );
}
