'use client';

// Settings → Capabilities. Read-only overview of what's installed.
// Three groupings (ingest_source / slash_command / action_button)
// with each entry showing source extension + a runtime badge.

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Activity, Command, MousePointerClick } from 'lucide-react';
import { useAllCapabilities, type CapabilityListing } from '@/lib/capabilities';

const KIND_META: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; blurb: string }> = {
  ingest_source: {
    label: 'Ingest sources',
    icon: Activity,
    blurb: 'Pull external data into the bench. Run on a schedule.',
  },
  slash_command: {
    label: 'Slash commands',
    icon: Command,
    blurb: 'Palette entries (⌘K) that trigger actions or jump to surfaces.',
  },
  action_button: {
    label: 'Action buttons',
    icon: MousePointerClick,
    blurb: 'Contextual buttons rendered on items — knowledge nodes today.',
  },
};

export function CapabilitiesCard() {
  const { data, error, isLoading } = useAllCapabilities();

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Installed capabilities</CardTitle>
        <CardDescription className="text-xs">
          Every capability declared by a loaded extension. Items marked
          “runtime ready” have a registered handler; “declared” means the
          manifest is forward-compatible but the runtime hasn’t shipped
          yet.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {isLoading && (
          <p className="text-xs text-muted-foreground">Loading…</p>
        )}
        {error && (
          <p className="text-xs text-destructive">
            Failed to load capabilities: {(error as Error).message}
          </p>
        )}
        {data && (Object.keys(KIND_META) as Array<keyof typeof KIND_META>).map((kind) => {
          const items = (data as Record<string, CapabilityListing[]>)[kind] || [];
          const meta = KIND_META[kind];
          const Icon = meta.icon;
          return (
            <section key={kind} className="space-y-2">
              <div className="flex items-center gap-2">
                <Icon className="w-3.5 h-3.5 text-violet-300" />
                <h3 className="text-sm font-medium">{meta.label}</h3>
                <span className="text-[10px] text-muted-foreground">
                  · {items.length}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground/80 -mt-1">
                {meta.blurb}
              </p>
              {items.length === 0 ? (
                <p className="text-xs text-muted-foreground italic pl-5">
                  None declared.
                </p>
              ) : (
                <ul className="space-y-1.5 pl-5">
                  {items.map((cap) => (
                    <CapabilityRow key={`${cap.extension}/${cap.name}`} cap={cap} />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}

function CapabilityRow({ cap }: { cap: CapabilityListing }) {
  const label =
    (cap.config as { label?: string })?.label ||
    cap.name.replace(/_/g, ' ');
  return (
    <li className="flex items-start gap-2 text-xs">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium">{label}</span>
          <Badge
            variant="outline"
            className={
              cap.runner_registered
                ? 'text-[9px] text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
                : 'text-[9px] text-amber-300 border-amber-500/40 bg-amber-500/10'
            }
          >
            {cap.runner_registered ? 'runtime ready' : 'declared'}
          </Badge>
          <span className="text-[10px] text-muted-foreground">
            from {cap.extension}
          </span>
        </div>
        {cap.description && (
          <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
            {cap.description}
          </p>
        )}
      </div>
    </li>
  );
}
