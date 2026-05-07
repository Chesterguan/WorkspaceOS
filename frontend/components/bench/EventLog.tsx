'use client';

import { useState, useEffect, useRef } from 'react';
import { useEventStream } from '@/lib/bench/useEventStream';
import { humanize, levelColor, formatTime } from '@/lib/bench/humanize';

const LEVEL_FILTERS = ['all', 'info', 'success', 'warn', 'error'] as const;
type LevelFilter = typeof LEVEL_FILTERS[number];

export function EventLog() {
  const events = useEventStream();
  const [filter, setFilter] = useState<LevelFilter>('all');
  const [paused, setPaused] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (paused) return;
    containerRef.current?.scrollTo({ top: containerRef.current.scrollHeight });
  }, [events.length, paused]);

  const filtered = filter === 'all' ? events : events.filter((e) => e.level === filter);

  return (
    <div
      className="flex h-full flex-col"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="flex items-center gap-2 border-b border-[#1a1a1a] bg-[#0f0f0f] px-3 py-2 font-mono text-[10px] text-[#888]">
        <span>events</span>
        <div className="flex-1" />
        {LEVEL_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded px-1.5 py-0.5 ${filter === f ? 'bg-[#1a1a1a] text-[#ddd]' : 'hover:text-[#ccc]'}`}
          >
            {f}
          </button>
        ))}
      </div>
      <div ref={containerRef} className="flex-1 overflow-y-auto px-3 py-2 font-mono text-[10px] leading-snug">
        {filtered.length === 0 ? (
          <div className="text-[#555]">waiting for events…</div>
        ) : (
          filtered.map((e, i) => (
            <div key={i} style={{ color: levelColor(e.level) }} className="whitespace-pre-wrap">
              <span className="text-[#666] mr-1">{formatTime(e.ts)}</span>
              {humanize(e)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
