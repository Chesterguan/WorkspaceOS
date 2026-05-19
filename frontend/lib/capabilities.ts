'use client';

// Capability discovery + dispatch — frontend mirror of /api/v1/capabilities/*.
// Used by:
//   - Settings → Capabilities tab (full list)
//   - CommandPalette (slash_command entries)
//   - KG node renderer + future item renderers (action_button entries)

import { useCallback } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

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

async function fetcher(path: string) {
  const res = await fetch(`${BASE_URL}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

// ── Types ────────────────────────────────────────────────────────────

export type CapabilityKind =
  | 'ingest_source' | 'slash_command' | 'action_button' | 'surface_widget';

export interface CapabilityListing {
  extension: string;
  kind: CapabilityKind;
  name: string;
  description?: string | null;
  config: Record<string, unknown>;
  runner_registered: boolean;
}

export interface SlashCommandInput {
  name: string;
  label: string;
  type: 'text' | 'textarea' | 'number';
  required?: boolean;
  placeholder?: string;
}

export interface SlashCommandEntry {
  id: string;
  name: string;
  label: string;
  keywords: string[];
  icon?: string | null;
  handler_kind: 'api_call' | 'navigate';
  handler_target: string;
  inputs?: SlashCommandInput[];
  source_extension: string;
}

export interface ActionButtonEntry {
  id: string;
  name: string;
  label: string;
  icon?: string | null;
  target: string;
  visible_when: Record<string, unknown>;
  source_extension: string;
}

// ── Hooks ────────────────────────────────────────────────────────────

export function useAllCapabilities() {
  return useSWR<Record<CapabilityKind, CapabilityListing[]>>(
    '/capabilities',
    fetcher,
    { revalidateOnFocus: false },
  );
}

export function useSlashCommands() {
  return useSWR<SlashCommandEntry[]>(
    '/capabilities/slash-commands',
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 30_000 },
  );
}

export function useItemActions(target: string | null) {
  return useSWR<ActionButtonEntry[]>(
    target ? `/capabilities/actions?target=${encodeURIComponent(target)}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 30_000 },
  );
}

// ── Dispatchers ──────────────────────────────────────────────────────

export async function triggerSlashRunner(
  name: string,
  payload: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE_URL}/capabilities/runners/${name}/trigger`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`runner ${name} failed: ${res.status} ${body}`);
  }
  return res.json();
}

export async function invokeAction(
  name: string,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE_URL}/capabilities/actions/${name}/invoke`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`action ${name} failed: ${res.status} ${body}`);
  }
  return res.json();
}

// ── Visibility predicate ─────────────────────────────────────────────

/** Evaluate an action's `visible_when` clause against an item.
 *  All listed fields must match (AND). Each field can be either an
 *  exact value or an array of accepted values (OR within field).
 *  Empty/missing visible_when = always visible. */
export function actionVisible(
  visibleWhen: Record<string, unknown> | undefined,
  item: Record<string, unknown>,
): boolean {
  if (!visibleWhen || Object.keys(visibleWhen).length === 0) return true;
  for (const [key, allowed] of Object.entries(visibleWhen)) {
    const actual = item[key];
    if (Array.isArray(allowed)) {
      if (!allowed.includes(actual as never)) return false;
    } else {
      if (actual !== allowed) return false;
    }
  }
  return true;
}

// ── Dispatch helper used by palette + buttons (with toast handling) ──

export function useCapabilityDispatcher() {
  return useCallback(async (
    handlerKind: 'api_call' | 'navigate',
    handlerTarget: string,
    onNavigate: (path: string) => void,
    payload: Record<string, unknown> = {},
  ) => {
    if (handlerKind === 'navigate') {
      onNavigate(handlerTarget);
      return;
    }
    // api_call: split out the runner name from the path /capabilities/runners/<name>/trigger
    const m = handlerTarget.match(/\/capabilities\/runners\/([^/]+)\/trigger/);
    if (!m) {
      toast.error(`Unsupported handler_target: ${handlerTarget}`);
      return;
    }
    try {
      const result = await triggerSlashRunner(m[1], payload);
      const t = (result as Record<string, unknown>).toast;
      if (typeof t === 'string') toast.success(t);
    } catch (err) {
      toast.error((err as Error).message);
    }
  }, []);
}
