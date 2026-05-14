'use client';

// Settings → Capabilities. Lists installed capabilities, grouped by
// kind. Each ingest_source row has a Configure button → modal form
// that edits the encrypted DB overlay (no YAML editing, no restart).

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Activity, Command, MousePointerClick, ExternalLink, Settings2 } from 'lucide-react';
import { useAllCapabilities, type CapabilityListing } from '@/lib/capabilities';
import { ConfigureCapabilityModal } from '@/components/capabilities/ConfigureCapabilityModal';

// Extension id → docs path on the GitHub repo. Used to wire each
// capability listing to its setup guide. Update when new extensions
// ship with non-trivial configuration.
const SETUP_GUIDE_PATHS: Record<string, string> = {
  'local-files-watcher': 'docs/extensions/local-files.md',
  'macos-mail':          'docs/extensions/macos-mail.md',
  benchling:             'docs/extensions/benchling.md',
  zotero:                'docs/extensions/zotero.md',
};
const SETUP_GUIDE_INDEX = 'docs/extensions/SETUP.md';
const REPO_URL = 'https://github.com/Chesterguan/WorkspaceOS/blob/main';

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

interface ConfigureTarget {
  extensionId: string;
  capabilityName: string;
  label: string;
}

export function CapabilitiesCard() {
  const { data, error, isLoading } = useAllCapabilities();
  const [configuring, setConfiguring] = useState<ConfigureTarget | null>(null);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Installed capabilities</CardTitle>
            <CardDescription className="text-xs">
              Every capability declared by a loaded extension. Items marked
              <span className="mx-1 text-emerald-300">runtime ready</span>
              have a registered handler; <span className="mx-1 text-amber-300">declared</span>
              means the manifest is forward-compatible but the runtime
              hasn&apos;t shipped yet. Each row links to its setup guide.
            </CardDescription>
          </div>
          <a
            href={`${REPO_URL}/${SETUP_GUIDE_INDEX}`}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] text-violet-300 hover:text-violet-200 whitespace-nowrap inline-flex items-center gap-1"
          >
            All setup guides
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
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
                    <CapabilityRow
                      key={`${cap.extension}/${cap.name}`}
                      cap={cap}
                      onConfigure={
                        cap.kind === 'ingest_source' && cap.runner_registered
                          ? () => setConfiguring({
                              extensionId: cap.extension,
                              capabilityName: cap.name,
                              label: (cap.config as { label?: string })?.label
                                || cap.name.replace(/_/g, ' '),
                            })
                          : undefined
                      }
                    />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </CardContent>
      {configuring && (
        <ConfigureCapabilityModal
          extensionId={configuring.extensionId}
          capabilityName={configuring.capabilityName}
          capabilityLabel={configuring.label}
          onClose={() => setConfiguring(null)}
        />
      )}
    </Card>
  );
}

function CapabilityRow({
  cap, onConfigure,
}: {
  cap: CapabilityListing;
  onConfigure?: () => void;
}) {
  const label =
    (cap.config as { label?: string })?.label ||
    cap.name.replace(/_/g, ' ');
  const guidePath = SETUP_GUIDE_PATHS[cap.extension];
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
          {onConfigure && (
            <button
              type="button"
              onClick={onConfigure}
              title="Edit credentials + settings in the UI (encrypted at rest)"
              className="inline-flex items-center gap-0.5 text-[10px] text-violet-300 hover:text-violet-200 underline-offset-2 hover:underline"
            >
              <Settings2 className="w-2.5 h-2.5" />
              configure
            </button>
          )}
          {guidePath && (
            <a
              href={`${REPO_URL}/${guidePath}`}
              target="_blank"
              rel="noreferrer"
              title={`Setup guide for ${cap.extension}`}
              className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground"
            >
              docs
              <ExternalLink className="w-2.5 h-2.5" />
            </a>
          )}
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
