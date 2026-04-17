"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { appSettings } from "@/lib/api";
import type { KeyStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Key, Loader2, Pencil, Trash2 } from "lucide-react";

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

export function ApiKeysCard() {
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
