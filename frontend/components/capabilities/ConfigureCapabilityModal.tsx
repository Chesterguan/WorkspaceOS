'use client';

// Per-capability config form. Reads + writes the DB overlay; sensitive
// fields stay masked unless the user types into them. Two assistant
// affordances:
//   - Auto-fill: posts current config to /auto-fill, merges any derived
//     values into the form (e.g. Zotero: API key → library_id).
//   - Test: runs the capability once and reports success/failure.

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Wand2, FlaskConical, X } from 'lucide-react';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9000/api/v1';

function authHeaders(): Record<string, string> {
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  else if (apiKey) h['X-API-Key'] = apiKey;
  return h;
}

interface Props {
  extensionId: string;
  capabilityName: string;
  capabilityLabel: string;
  onClose: () => void;
}

interface ConfigResponse {
  config: Record<string, unknown>;
  overlay_keys: string[];
}

const SENSITIVE_KEYS = new Set([
  'api_key', 'api_token', 'token', 'access_token',
  'password', 'secret', 'client_secret',
]);

// Per-capability field help — small inline hints under each input.
// Frontend-owned because a non-CS user won't read the docs page; they
// need the explanation right next to the field. Expandable to a
// data-source-from-backend later.
const FIELD_HELP: Record<string, Record<string, string>> = {
  benchling_import: {
    api_key: 'Benchling Settings → API keys → Create new API key. Permissions: notebook read.',
    tenant: 'Your subdomain. For lab.benchling.com use "lab.benchling.com" (no https://).',
    days_back: 'How many days of recent entries to pull each tick. Default 14.',
    page_size: 'Items per API call. Max 100.',
  },
  zotero_sync: {
    api_key: 'zotero.org/settings/keys → Create new private key. Allow library access.',
    library_id: 'Your Zotero userID (shown on the API keys page). Click Auto-fill to derive.',
    library_type: '"user" for personal library, "group" for a group library.',
    items_limit: 'Items per tick. Max 100. Default 100.',
  },
  local_files: {
    watch_path: 'Directory inside the backend container. Default /projects — set WORKSPACE_HOST_PATH in .env to control the bind-mount source.',
    poll_interval_seconds: 'How often to walk the directory. Default 30.',
    max_files_per_tick: 'Cap to prevent floods on first run. Default 100.',
    max_size_mb: 'Skip files larger than this. Default 1.0.',
  },
};

function isAutoFillSupported(capabilityName: string): boolean {
  return capabilityName === 'zotero_sync';
}

export function ConfigureCapabilityModal({
  extensionId, capabilityName, capabilityLabel, onClose,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [autoFilling, setAutoFilling] = useState(false);
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [overlayKeys, setOverlayKeys] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `${BASE_URL}/capabilities/${extensionId}/${capabilityName}/config`,
          { headers: authHeaders() },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: ConfigResponse = await res.json();
        if (!cancelled) {
          setConfig(data.config);
          setOverlayKeys(data.overlay_keys);
          setLoading(false);
        }
      } catch (err) {
        toast.error(`Couldn't load config: ${(err as Error).message}`);
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [extensionId, capabilityName]);

  function setField(key: string, value: string) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  async function save() {
    setSaving(true);
    try {
      const res = await fetch(
        `${BASE_URL}/capabilities/${extensionId}/${capabilityName}/config`,
        {
          method: 'PUT',
          headers: authHeaders(),
          body: JSON.stringify({ config }),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      toast.success('Saved. Next ingest tick will use the new config.');
      setOverlayKeys(data.overlay_keys || []);
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    try {
      // Save first so the test uses the values currently in the form,
      // not stale state.
      await fetch(
        `${BASE_URL}/capabilities/${extensionId}/${capabilityName}/config`,
        {
          method: 'PUT',
          headers: authHeaders(),
          body: JSON.stringify({ config }),
        },
      );
      const res = await fetch(
        `${BASE_URL}/capabilities/${extensionId}/${capabilityName}/test`,
        { method: 'POST', headers: authHeaders() },
      );
      const data = await res.json();
      if (data.success) {
        toast.success(`Test passed — ${data.message}`);
      } else {
        toast.error(`Test failed: ${data.message || 'unknown error'}`);
      }
    } catch (err) {
      toast.error(`Test errored: ${(err as Error).message}`);
    } finally {
      setTesting(false);
    }
  }

  async function autoFill() {
    setAutoFilling(true);
    try {
      const res = await fetch(
        `${BASE_URL}/capabilities/${extensionId}/${capabilityName}/auto-fill`,
        {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({ config }),
        },
      );
      const data = await res.json();
      const derived = (data.derived || {}) as Record<string, unknown>;
      if (Object.keys(derived).length > 0) {
        setConfig((prev) => ({ ...prev, ...derived }));
        toast.success(data.message || 'Auto-fill applied.');
      } else {
        toast.message(data.message || 'No derivable values to auto-fill.');
      }
    } catch (err) {
      toast.error(`Auto-fill errored: ${(err as Error).message}`);
    } finally {
      setAutoFilling(false);
    }
  }

  const fieldKeys = Object.keys(config);
  const help = FIELD_HELP[capabilityName] || {};
  const autoFillOk = isAutoFillSupported(capabilityName);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/40 p-4 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-xl rounded-lg border border-border bg-card shadow-xl my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">Configure {capabilityLabel}</h2>
            <p className="text-[11px] text-muted-foreground">
              {extensionId} · {capabilityName}. Values save to encrypted DB —
              no need to edit YAML or restart.
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {loading ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : fieldKeys.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              This capability has no editable config fields.
            </p>
          ) : (
            fieldKeys.map((key) => {
              const isSensitive = SENSITIVE_KEYS.has(key);
              const fromOverlay = overlayKeys.includes(key);
              const value = String(config[key] ?? '');
              return (
                <div key={key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-medium text-muted-foreground">
                      {key}
                      {fromOverlay && (
                        <span className="ml-1.5 text-[9px] text-emerald-300">
                          (saved)
                        </span>
                      )}
                    </label>
                  </div>
                  <Input
                    type={isSensitive ? 'password' : 'text'}
                    value={value}
                    onChange={(e) => setField(key, e.target.value)}
                    placeholder={isSensitive && value === '***' ? '***' : ''}
                    className="bg-card/40 border-border/60 h-9 text-sm font-mono"
                  />
                  {help[key] && (
                    <p className="text-[10px] text-muted-foreground/80">{help[key]}</p>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="border-t border-border/60 px-4 py-3 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            {autoFillOk && (
              <Button
                variant="ghost"
                size="sm"
                onClick={autoFill}
                disabled={loading || autoFilling || saving || testing}
                className="gap-1.5"
                title="Use the API key to derive other fields"
              >
                <Wand2 className="w-3.5 h-3.5" />
                {autoFilling ? 'Auto-filling…' : 'Auto-fill'}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={test}
              disabled={loading || autoFilling || saving || testing}
              className="gap-1.5"
              title="Run one ingest tick with the current config"
            >
              <FlaskConical className="w-3.5 h-3.5" />
              {testing ? 'Testing…' : 'Test'}
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={save}
              disabled={loading || saving}
              className="bg-violet-500 hover:bg-violet-600"
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
