import type { BenchEvent } from './useEventStream';

export function humanize(event: BenchEvent): string {
  const meta = event.meta ?? {};
  switch (event.source) {
    case 'extract': {
      const n = meta.nodes ?? '';
      const project = meta.project_name ?? 'a project';
      return `Saved ${n} item${n === 1 ? '' : 's'} from ${project}`;
    }
    case 'ai.complete': {
      const model = (meta.model as string | undefined) ?? 'AI';
      const ms = meta.latency_ms;
      return `${model} replied${ms ? ` · ${ms}ms` : ''}`;
    }
    case 'sync': {
      const commits = meta.commits ?? '';
      const project = meta.project_name ?? '';
      return `Pulled ${commits} commits from ${project}`.trim();
    }
    case 'worklog':
      return `Generated ${meta.period ?? 'weekly'} worklog`;
    case 'paper':
      return `Paper · ${event.summary}`;
    case 'cron':
      return event.summary;
    case 'error':
      return `Hit a glitch (${event.summary})`;
    default:
      return event.summary;
  }
}

export function levelColor(level: BenchEvent['level']): string {
  switch (level) {
    case 'success': return '#5a5';
    case 'warn':    return '#a85';
    case 'error':   return '#a55';
    default:        return '#5aa';
  }
}

export function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toTimeString().slice(0, 5);
}
