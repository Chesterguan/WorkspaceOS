'use client';

// Renders the GeneratedConfig in human-readable cards so the user can
// eyeball what's being applied. No YAML is shown by default — there's
// an "Inspect YAML" disclosure for the curious. The Apply / Regenerate
// buttons live at the bottom; both stay disabled while a write is in flight.

import { useState } from 'react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { GeneratedConfig } from '@/lib/onboarding/types';

interface Props {
  config: GeneratedConfig;
  applying: boolean;
  onApply: () => void;
  onRegenerate: () => void;
}

export function PreviewPane({ config, applying, onApply, onRegenerate }: Props) {
  const [yamlOpen, setYamlOpen] = useState(false);
  const enabledSurfaces = config.surfaces.filter((s) => s.enabled);
  const disabledSurfaces = config.surfaces.filter((s) => !s.enabled);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="flex flex-col gap-6 max-w-2xl w-full mx-auto"
    >
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Here&apos;s your workbench
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {config.app.tagline ?? 'Configurable single-surface workbench'} ·
          accent <span className="font-mono" style={{ color: config.app.accent }}>
            {config.app.accent}
          </span>
        </p>
      </div>

      {/* Surfaces */}
      <Section title="Surfaces" subtitle={`${enabledSurfaces.length} enabled`}>
        <div className="flex flex-wrap gap-2">
          {enabledSurfaces.map((s) => (
            <SurfaceChip key={s.id} letter={s.letter} label={s.label} accent={s.accent} />
          ))}
          {disabledSurfaces.length > 0 && (
            <div className="w-full mt-3 text-xs text-muted-foreground/70">
              Off:{' '}
              {disabledSurfaces.map((s) => s.label).join(', ')}
            </div>
          )}
        </div>
      </Section>

      {/* Persona pools */}
      {config.persona_pools.map((pool) => (
        <Section
          key={pool.pool_id}
          title={`${pool.label} advisors`}
          subtitle={`${pool.personas.length} personas`}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {pool.personas.map((p) => (
              <div
                key={p.id}
                className="rounded-lg border border-border/50 bg-card/30 p-3"
              >
                <div className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: p.color }}
                  />
                  <span className="text-sm font-medium">{p.name}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">
                  {p.system_prompt}
                </p>
              </div>
            ))}
          </div>
        </Section>
      ))}

      {/* Taxonomy */}
      <Section
        title="Knowledge taxonomy"
        subtitle={`${config.taxonomy.node_types.length} node types · ${config.taxonomy.edge_types.length} edge types`}
      >
        <div className="flex flex-wrap gap-1.5">
          {config.taxonomy.node_types.map((n) => (
            <span
              key={n.id}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs"
              style={{
                backgroundColor: `${n.color}22`,
                color: n.color,
                border: `1px solid ${n.color}55`,
              }}
            >
              {n.label}
            </span>
          ))}
        </div>
      </Section>

      {/* Worklog templates */}
      {Object.keys(config.worklog_templates).length > 0 && (
        <Section
          title="Worklog templates"
          subtitle={`${Object.keys(config.worklog_templates).length} cadence${
            Object.keys(config.worklog_templates).length === 1 ? '' : 's'
          }`}
        >
          {Object.entries(config.worklog_templates).slice(0, 1).map(([cadence, text]) => (
            <div key={cadence}>
              <div className="text-xs text-muted-foreground mb-1.5 capitalize">
                {cadence} · sample
              </div>
              <pre className="text-[11px] font-mono bg-card/30 border border-border/40 rounded p-2.5 whitespace-pre-wrap overflow-hidden line-clamp-4">
                {text}
              </pre>
            </div>
          ))}
        </Section>
      )}

      {/* YAML disclosure */}
      <button
        onClick={() => setYamlOpen((v) => !v)}
        className="self-start text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {yamlOpen ? '↑ Hide YAML' : '↓ Inspect raw YAML'}
      </button>
      {yamlOpen && (
        <div className="space-y-3">
          {Object.entries(config.raw_files).map(([path, content]) => (
            <div key={path}>
              <div className="text-[11px] font-mono text-muted-foreground mb-1">
                {path}
              </div>
              <pre className="text-[11px] font-mono bg-card/20 border border-border/30 rounded p-3 whitespace-pre-wrap overflow-x-auto">
                {content}
              </pre>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2 border-t border-border/40">
        <Button
          onClick={onApply}
          disabled={applying}
          className="bg-violet-500 hover:bg-violet-600"
        >
          {applying ? 'Applying…' : 'Apply this config'}
        </Button>
        <Button
          variant="ghost"
          onClick={onRegenerate}
          disabled={applying}
        >
          Regenerate
        </Button>
      </div>
    </motion.div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-baseline gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {subtitle && (
          <span className="text-xs text-muted-foreground">{subtitle}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function SurfaceChip({
  letter,
  label,
  accent,
}: {
  letter: string;
  label: string;
  accent: string;
}) {
  // Accent strings from config are tailwind palette names like 'violet'.
  const cls = cn(
    'inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs',
    accent === 'violet' && 'border-violet-500/40 bg-violet-500/10 text-violet-200',
    accent === 'blue' && 'border-blue-500/40 bg-blue-500/10 text-blue-200',
    accent === 'orange' && 'border-orange-500/40 bg-orange-500/10 text-orange-200',
    accent === 'teal' && 'border-teal-500/40 bg-teal-500/10 text-teal-200',
    accent === 'emerald' && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  );
  return (
    <span className={cls}>
      <span className="font-mono font-bold text-[10px]">{letter}</span>
      <span>{label}</span>
    </span>
  );
}
