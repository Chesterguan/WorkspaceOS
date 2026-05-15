'use client';

// Per-capability config form. Reads + writes the DB overlay; sensitive
// fields stay masked unless the user types into them. Two assistant
// affordances:
//   - Auto-fill: posts current config to /auto-fill, merges any derived
//     values into the form (e.g. Zotero: API key → library_id).
//   - Test: runs the capability once and reports success/failure.

import { useEffect, useRef, useState } from 'react';
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

// Per-capability, per-field metadata. Frontend-owned because a non-CS
// user won't read a docs page — they need a plain label, a one-line
// explanation, a "where do I get this" link, and (for list fields) a
// checkbox picker right next to the input. This is the same treatment
// the AI & API Keys card got; the cold-open UX test showed the raw
// `entity_types` free-text field was undiscoverable.
interface FieldMeta {
  label?: string; // human label; falls back to a humanized key
  help?: string; // plain-language one-liner
  getUrl?: string; // "where to get this" external link
  getLabel?: string; // link text (default "Where to get this")
  kind?: 'multiselect'; // special input rendering
  options?: { value: string; label: string; hint?: string }[];
}

const FIELD_META: Record<string, Record<string, FieldMeta>> = {
  benchling_import: {
    api_key: {
      label: 'Benchling API key',
      help: 'A token that lets WorkspaceOS read your Benchling data. It is stored encrypted.',
      getUrl: 'https://benchling.com',
      getLabel: 'Benchling → Settings → API keys → Create new key (notebook read)',
    },
    tenant: {
      label: 'Your Benchling address',
      help: 'Just the part before benchling.com. If you log in at lab.benchling.com, enter "lab.benchling.com" — no https://.',
    },
    entity_types: {
      label: 'What to pull from Benchling',
      help: 'Pick the kinds of Benchling data you want to appear in your knowledge graph.',
      kind: 'multiselect',
      options: [
        { value: 'entries', label: 'Notebook entries', hint: 'Your day-to-day lab notebook' },
        { value: 'dna_sequences', label: 'Plasmids / DNA sequences', hint: 'Your plasmid registry → Construct nodes' },
        { value: 'custom_entities', label: 'Strains / custom entities', hint: 'Needs the schema filter below' },
      ],
    },
    custom_entity_schemas: {
      label: 'Strain schema names (optional)',
      help: 'Only if you ticked "Strains" above. Type the Benchling schema name(s) to pull, e.g. "strain". Comma-separated, case-insensitive. Leave blank to skip strains.',
    },
    days_back: {
      label: 'How far back to look',
      help: 'Number of days of recent changes to pull each sync. Default 14.',
    },
    page_size: { label: 'Items per request', help: 'How many items to fetch per API call. Max 100.' },
  },
  zotero_sync: {
    api_key: {
      label: 'Zotero API key',
      help: 'A private key that lets WorkspaceOS read your Zotero library. Stored encrypted.',
      getUrl: 'https://www.zotero.org/settings/keys',
      getLabel: 'zotero.org → Settings → Keys → Create new private key',
    },
    library_id: {
      label: 'Zotero library ID',
      help: 'Your numeric Zotero userID (shown on the API keys page). Or click Auto-fill to derive it from your key.',
    },
    library_type: {
      label: 'Library type',
      help: 'Type "user" for your personal library, or "group" for a shared group library.',
    },
    items_limit: { label: 'Items per sync', help: 'Max items to pull each tick. Max 100. Default 100.' },
  },
  github_user_tools: {
    usernames: {
      label: 'GitHub usernames',
      help: 'The GitHub handle(s) whose public repos become Tool nodes. Comma-separated for multiple, e.g. "qiandemoni, labmate".',
    },
    token: {
      label: 'GitHub token (optional)',
      help: 'Only needed if you hit rate limits. A fine-grained token with public-repo read is enough.',
      getUrl: 'https://github.com/settings/personal-access-tokens/new',
      getLabel: 'GitHub → Settings → Developer settings → Fine-grained tokens',
    },
  },
  preprint_ingest: {
    keywords: {
      label: 'Topics to follow',
      help: 'Comma-separated phrases. A preprint is pulled if any phrase appears in its title/abstract, e.g. "plant cell wall, glucomannan, hemicellulose". Leave blank and nothing is pulled.',
    },
    sources: {
      label: 'Preprint servers',
      help: 'Which servers to watch. "biorxiv" for biology, "medrxiv" for clinical. Comma-separated.',
    },
    days_back: { label: 'How far back to look', help: 'Days of recent preprints to scan each run. Default 7.' },
  },
  local_files: {
    watch_path: {
      label: 'Folder to watch',
      help: 'A directory the backend can see. Default /projects. Changing this needs a Docker bind-mount — ask whoever set up your install.',
    },
    max_files_per_tick: { label: 'Max files per scan', help: 'Cap to avoid floods on first run. Default 100.' },
    max_size_mb: { label: 'Max file size (MB)', help: 'Skip files bigger than this. Default 1.0.' },
  },
  ot2_protocols: {
    watch_path: {
      label: 'Protocol folder',
      help: 'Folder of Opentrons .py protocols the backend can see. Default /protocols. Changing this needs a Docker bind-mount — ask whoever set up your install.',
    },
    recursive: { label: 'Include subfolders', help: 'true to walk subdirectories, false for top-level only.' },
  },
};

// Humanize a raw config key for display when there's no explicit label.
function humanizeKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\bseconds\b/i, '(seconds)')
    .replace(/^\w/, (c) => c.toUpperCase());
}

// Render a *_seconds interval as a human phrase, e.g. 21600 → "every 6 hours".
function intervalLabel(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const h = seconds / 3600;
  const m = seconds / 60;
  if (h >= 1 && Number.isInteger(h)) return `= every ${h} hour${h === 1 ? '' : 's'}`;
  if (m >= 1 && Number.isInteger(m)) return `= every ${m} minute${m === 1 ? '' : 's'}`;
  return `= every ${seconds}s`;
}

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
  const metaForCap = FIELD_META[capabilityName] || {};
  const autoFillOk = isAutoFillSupported(capabilityName);

  function toggleMultiValue(key: string, optionValue: string) {
    setConfig((prev) => {
      const cur = prev[key];
      const arr: string[] = Array.isArray(cur)
        ? (cur as string[])
        : typeof cur === 'string' && cur
          ? cur.split(',').map((s) => s.trim()).filter(Boolean)
          : [];
      const nextArr = arr.includes(optionValue)
        ? arr.filter((v) => v !== optionValue)
        : [...arr, optionValue];
      return { ...prev, [key]: nextArr };
    });
  }

  // a11y plumbing: Escape closes, focus returns to the trigger that
  // opened the modal, and the dialog is announced by its h2 title.
  //
  // We deliberately run this effect mount-only (`[]` deps). Parents
  // typically pass `onClose={() => setX(null)}` — a fresh lambda each
  // render — and if we put `onClose` in the deps the effect would
  // re-fire on every parent rerender, stealing focus mid-typing and
  // overwriting `triggerRef` with whatever the user last touched.
  // Reading `onClose` through a ref keeps it current without that
  // re-binding cost.
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    triggerRef.current = (document.activeElement as HTMLElement) || null;
    // Focus the first focusable element inside the panel so keyboard
    // users land somewhere predictable.
    const firstFocusable = panelRef.current?.querySelector<HTMLElement>(
      'input[name^="cap-"], button:not([tabindex="-1"]), [href], select, textarea',
    );
    firstFocusable?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
      }
    }
    document.addEventListener('keydown', onKey);
    const captured = triggerRef.current;
    return () => {
      document.removeEventListener('keydown', onKey);
      // Return focus to whatever opened the modal — keyboard users
      // shouldn't have to re-find their place after Close. Use the
      // captured value so we don't get fooled by mid-life overwrites.
      captured?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/40 p-4 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="cfg-modal-title"
    >
      <div
        ref={panelRef}
        className="w-full max-w-xl rounded-lg border border-border bg-card shadow-xl my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div>
            <h2 id="cfg-modal-title" className="text-sm font-semibold">Configure {capabilityLabel}</h2>
            <p className="text-[11px] text-muted-foreground">
              {extensionId} · {capabilityName}. Values save to encrypted DB —
              no need to edit YAML or restart.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Decoy inputs — Chromium autofill heuristic looks for a
              text+password pair and fills the text with the user's
              email regardless of autoComplete="off". By putting the
              first password-typed input here (off-screen), the
              autofill targets these and leaves the real fields alone.
              Standard workaround used by many SaaS settings pages. */}
          <div style={{ position: 'absolute', top: -1000, left: -1000, opacity: 0 }} aria-hidden="true">
            <input type="text" name="username" tabIndex={-1} autoComplete="username" />
            <input type="password" name="password" tabIndex={-1} autoComplete="current-password" />
          </div>

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
              const meta = metaForCap[key] || {};
              const label = meta.label || humanizeKey(key);
              const rawVal = config[key];
              const value = Array.isArray(rawVal)
                ? (rawVal as string[]).join(', ')
                : String(rawVal ?? '');
              const selectedSet = new Set(
                Array.isArray(rawVal)
                  ? (rawVal as string[])
                  : typeof rawVal === 'string' && rawVal
                    ? rawVal.split(',').map((s) => s.trim()).filter(Boolean)
                    : [],
              );
              const intervalHint =
                key.endsWith('_seconds') && value && Number(value)
                  ? intervalLabel(Number(value))
                  : '';
              return (
                <div key={key} className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <label className="text-xs font-medium text-foreground">
                      {label}
                    </label>
                    {fromOverlay && (
                      <span className="text-[9px] text-emerald-300">saved</span>
                    )}
                    {meta.getUrl && (
                      <a
                        href={meta.getUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 text-[10px] text-violet-400 hover:text-violet-300"
                      >
                        {meta.getLabel || 'Where to get this'} ↗
                      </a>
                    )}
                  </div>

                  {meta.kind === 'multiselect' && meta.options ? (
                    <div className="space-y-1.5 rounded-md border border-border/60 bg-card/40 p-2.5">
                      {meta.options.map((opt) => (
                        <label
                          key={opt.value}
                          className="flex items-start gap-2 cursor-pointer text-xs"
                        >
                          <input
                            type="checkbox"
                            checked={selectedSet.has(opt.value)}
                            onChange={() => toggleMultiValue(key, opt.value)}
                            className="mt-0.5 accent-violet-500"
                          />
                          <span>
                            <span className="text-foreground">{opt.label}</span>
                            {opt.hint && (
                              <span className="block text-[10px] text-muted-foreground/80">
                                {opt.hint}
                              </span>
                            )}
                          </span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <Input
                      type={isSensitive ? 'password' : 'text'}
                      value={value}
                      onChange={(e) => setField(key, e.target.value)}
                      placeholder={isSensitive && value === '***' ? '***' : ''}
                      // Disable browser autofill — otherwise the browser
                      // fills these narrow config values with saved
                      // emails/passwords.
                      autoComplete="off"
                      spellCheck={false}
                      autoCorrect="off"
                      name={`cap-${key}-${Math.random().toString(36).slice(2, 7)}`}
                      className="bg-card/40 border-border/60 h-9 text-sm font-mono"
                    />
                  )}

                  {meta.help && (
                    <p className="text-[10px] text-muted-foreground/80">{meta.help}</p>
                  )}
                  {intervalHint && (
                    <p className="text-[10px] text-violet-300/80">{intervalHint}</p>
                  )}
                  {!meta.label && !meta.help && (
                    <p className="text-[9px] text-muted-foreground/50 font-mono">{key}</p>
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
