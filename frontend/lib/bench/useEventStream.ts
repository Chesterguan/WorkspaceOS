'use client';

import { useEffect, useRef, useState } from 'react';

export interface BenchEvent {
  ts: number;
  level: 'info' | 'success' | 'warn' | 'error';
  source: string;
  summary: string;
  project_id?: string | null;
  meta?: Record<string, unknown>;
}

const MAX_HISTORY = 500;

export function useEventStream() {
  const [events, setEvents] = useState<BenchEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8989/api/v1';
    const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? '';
    const url = `${baseUrl}/events/stream?api_key=${encodeURIComponent(apiKey)}`;

    const es = new EventSource(url, { withCredentials: false });
    sourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: BenchEvent = JSON.parse(e.data);
        setEvents((prev) => {
          const next = [...prev, event];
          return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
        });
      } catch {
        // ignore malformed
      }
    };

    es.onerror = () => {
      // Browser will auto-reconnect; nothing to do.
    };

    return () => {
      es.close();
      sourceRef.current = null;
    };
  }, []);

  return events;
}
