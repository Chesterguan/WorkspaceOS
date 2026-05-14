// API wrappers for onboarding. /config/generate is SSE — we use fetch
// with a ReadableStream reader instead of EventSource because we need
// to send the answers as JSON in the request body, and EventSource is
// GET-only.

import { mutate } from 'swr';
import type { GeneratedConfig, OnboardingAnswers } from './types';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9000/api/v1';

function authHeaders(): Record<string, string> {
  // Mirrors lib/api.ts:apiFetch — token lives at localStorage['auth_token'].
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  else if (apiKey) headers['X-API-Key'] = apiKey;
  return headers;
}

export interface OnboardingState {
  tutorial_completed: boolean;
  onboarding_answers: OnboardingAnswers | null;
}

export async function fetchOnboardingState(): Promise<OnboardingState> {
  const res = await fetch(`${BASE_URL}/config/onboarding/me`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`onboarding/me ${res.status}`);
  return res.json();
}

export async function applyConfig(rawFiles: Record<string, string>): Promise<void> {
  const res = await fetch(`${BASE_URL}/config/apply`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ raw_files: rawFiles }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`apply ${res.status}: ${body}`);
  }
  // Apply flipped tutorial_completed=true server-side. Write the
  // optimistic value into the SWR cache directly so the next /bench
  // mount reads fresh state without waiting for a network round-trip.
  // Without this, useFirstRunRedirect can read a stale `false` from a
  // prior mount and bounce the user right back to /onboarding.
  //
  // `mutate(key, value, { revalidate: true })` writes the value AND
  // schedules a background refetch — belt and braces against any
  // server-side state we haven't anticipated.
  await mutate(
    '/config/onboarding/me',
    (current?: OnboardingState): OnboardingState => ({
      tutorial_completed: true,
      onboarding_answers: current?.onboarding_answers ?? null,
    }),
    { revalidate: true },
  );
  // Domain config changed too — invalidate so the bench rail picks up
  // any new surfaces immediately.
  await mutate('/config/domain');
}

// --- SSE consumer for /config/generate ---

export interface GenerateCallbacks {
  onProgress: (caption: string) => void;
  onDone: (config: GeneratedConfig) => void;
  onError: (message: string) => void;
}

export interface GenerateController {
  abort: () => void;
}

export function generateConfig(
  answers: OnboardingAnswers,
  cbs: GenerateCallbacks,
): GenerateController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE_URL}/config/generate`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(answers),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const body = await res.text();
        cbs.onError(`generate ${res.status}: ${body || 'no body'}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // SSE frames are separated by a blank line; parse what we have
        let idx: number;
        // eslint-disable-next-line no-cond-assign
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          parseFrame(frame, cbs);
        }
      }
      // Flush any trailing frame (no terminal \n\n)
      if (buf.trim()) parseFrame(buf.trim(), cbs);
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      cbs.onError((err as Error).message);
    }
  })();

  return { abort: () => controller.abort() };
}

function parseFrame(frame: string, cbs: GenerateCallbacks) {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    // ignore other fields (id:, retry:, etc.)
  }
  const dataStr = dataLines.join('\n');
  if (!dataStr) return;
  try {
    const payload = JSON.parse(dataStr);
    if (event === 'progress') cbs.onProgress(payload.caption ?? '');
    else if (event === 'done') cbs.onDone(payload as GeneratedConfig);
    else if (event === 'error') cbs.onError(payload.message ?? 'unknown error');
  } catch {
    cbs.onError(`malformed SSE frame: ${dataStr.slice(0, 200)}`);
  }
}
