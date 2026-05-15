'use client';

// Individual question step components for the onboarding wizard. Each
// step renders one question, owns its own input UI, and reports the
// updated answers slice back via onChange. Steps are deliberately tiny
// — the wizard shell handles transitions, navigation, and persistence.

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  AUDIENCE_OPTIONS,
  OUTPUT_OPTIONS,
  type AudienceId,
  type Cadence,
  type OnboardingAnswers,
  type OutputId,
  type Stage,
} from '@/lib/onboarding/types';

interface StepProps {
  answers: OnboardingAnswers;
  onChange: (patch: Partial<OnboardingAnswers>) => void;
  onNext: () => void;
}

// ---------------------------------------------------------------------------
// 1 · Domain
// ---------------------------------------------------------------------------

const DOMAIN_MAX = 1000;

export function DomainStep({ answers, onChange, onNext }: StepProps) {
  const len = answers.domain.length;
  // Counter only appears once the answer is substantial, so it
  // reassures rather than nags. maxLength hard-stops at the backend's
  // limit so the wizard can never produce a 422 the user only
  // discovers after filling every step.
  const showCount = len > 500;
  const nearLimit = len > 900;
  return (
    <StepShell
      title="What field are you in?"
      lede="A sentence or two. Be specific where it helps — &lsquo;protein folding&rsquo; beats &lsquo;biology&rsquo;."
    >
      <Input
        autoFocus
        value={answers.domain}
        maxLength={DOMAIN_MAX}
        onChange={(e) => onChange({ domain: e.target.value.slice(0, DOMAIN_MAX) })}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && answers.domain.trim()) onNext();
        }}
        placeholder="e.g. medical imaging with diffusion models"
        className="text-lg h-14 px-5 bg-card/40 border-border/60 focus:border-violet-500/60"
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          We&apos;ll use this to pick your advisor panel, taxonomy, and prompt tone.
        </p>
        {showCount && (
          <span
            className={cn(
              'text-[11px] tabular-nums shrink-0',
              nearLimit ? 'text-amber-400' : 'text-muted-foreground/60',
            )}
          >
            {len}/{DOMAIN_MAX}
          </span>
        )}
      </div>
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// 2 · Primary outputs (multi-select)
// ---------------------------------------------------------------------------

export function OutputsStep({ answers, onChange }: StepProps) {
  const selected = new Set<OutputId>(answers.primary_outputs);
  const toggle = (id: OutputId) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange({ primary_outputs: Array.from(next) });
  };
  return (
    <StepShell
      title="What do you actually produce?"
      lede="Pick everything that fits. We&apos;ll only turn on the surfaces you need."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {OUTPUT_OPTIONS.map((opt) => (
          <ChoiceCard
            key={opt.id}
            selected={selected.has(opt.id)}
            label={opt.label}
            hint={opt.hint}
            onClick={() => toggle(opt.id)}
          />
        ))}
      </div>
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// 3 · Audience (multi-select)
// ---------------------------------------------------------------------------

export function AudienceStep({ answers, onChange }: StepProps) {
  const selected = new Set<AudienceId>(answers.audience);
  const toggle = (id: AudienceId) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange({ audience: Array.from(next) });
  };
  return (
    <StepShell
      title="Who are you talking to?"
      lede="Drives style, voice, and which advisor lens makes sense."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {AUDIENCE_OPTIONS.map((opt) => (
          <ChoiceCard
            key={opt.id}
            selected={selected.has(opt.id)}
            label={opt.label}
            hint={opt.hint}
            onClick={() => toggle(opt.id)}
          />
        ))}
      </div>
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// 4 · Advisor panel (free text, optional)
// ---------------------------------------------------------------------------

export function AdvisorStep({ answers, onChange }: StepProps) {
  const [skip, setSkip] = useState(answers.advisor_panel === null);
  return (
    <StepShell
      title="Dream advisor panel?"
      lede="Real names, archetypes, or vibes. We&apos;ll make personas out of whatever you give us. Or skip and let us pick."
    >
      <Textarea
        value={answers.advisor_panel ?? ''}
        onChange={(e) => {
          setSkip(false);
          onChange({ advisor_panel: e.target.value });
        }}
        placeholder="e.g. an unflinching reviewer, a kind mentor, an ops-obsessed operator…"
        rows={4}
        className="bg-card/40 border-border/60 focus:border-violet-500/60"
        disabled={skip}
      />
      <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
        <input
          type="checkbox"
          checked={skip}
          onChange={(e) => {
            setSkip(e.target.checked);
            onChange({ advisor_panel: e.target.checked ? null : '' });
          }}
          className="accent-violet-500"
        />
        Let WorkspaceOS pick for me
      </label>
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// 5 · Tracked artifacts (free text, optional)
// ---------------------------------------------------------------------------

export function TrackedStep({ answers, onChange }: StepProps) {
  return (
    <StepShell
      title="What do you want to track over time?"
      lede="Decisions, claims, experiments, customer interviews… anything that feels worth a thread. Drives your knowledge graph."
    >
      <Textarea
        value={answers.tracked_artifacts ?? ''}
        onChange={(e) => onChange({ tracked_artifacts: e.target.value })}
        placeholder="e.g. decisions I made, hypotheses I&apos;m testing, interview snippets from users…"
        rows={4}
        className="bg-card/40 border-border/60 focus:border-violet-500/60"
      />
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// 6 · Cadence
// ---------------------------------------------------------------------------

const CADENCE_OPTIONS: { id: Cadence; label: string; hint: string }[] = [
  { id: 'weekly', label: 'Weekly', hint: 'Short, frequent check-ins' },
  { id: 'monthly', label: 'Monthly', hint: 'Mid-form retrospectives' },
  { id: 'quarterly', label: 'Quarterly', hint: 'Strategic, narrative-heavy' },
  { id: 'none', label: 'Skip worklog', hint: 'No reports for now' },
];

export function CadenceStep({ answers, onChange }: StepProps) {
  return (
    <StepShell
      title="How often do you want a progress report?"
      lede="Pick one. The worklog surface generates these from your activity + knowledge graph."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {CADENCE_OPTIONS.map((opt) => (
          <ChoiceCard
            key={opt.id}
            selected={answers.cadence === opt.id}
            label={opt.label}
            hint={opt.hint}
            onClick={() => onChange({ cadence: opt.id })}
          />
        ))}
      </div>
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// 7 · Stage (optional)
// ---------------------------------------------------------------------------

const STAGE_OPTIONS: { id: Stage; label: string; hint: string }[] = [
  { id: 'early', label: 'Early', hint: 'Figuring out what to build' },
  { id: 'mid', label: 'Mid', hint: 'Building & validating' },
  { id: 'late', label: 'Late', hint: 'Scaling or shipping to wider audience' },
];

export function StageStep({ answers, onChange }: StepProps) {
  return (
    <StepShell
      title="Where are you in this work?"
      lede="Adjusts the tone — early-stage advice sounds different from late-stage. Skip if it doesn't fit."
    >
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {STAGE_OPTIONS.map((opt) => (
          <ChoiceCard
            key={opt.id}
            selected={answers.stage === opt.id}
            label={opt.label}
            hint={opt.hint}
            onClick={() => onChange({ stage: opt.id })}
          />
        ))}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="text-xs text-muted-foreground self-start"
        onClick={() => onChange({ stage: null })}
      >
        Skip — don&apos;t use a stage hint
      </Button>
    </StepShell>
  );
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function StepShell({
  title,
  lede,
  children,
}: {
  title: string;
  lede: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-5 max-w-xl w-full mx-auto">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{lede}</p>
      </div>
      {children}
    </div>
  );
}

function ChoiceCard({
  selected,
  label,
  hint,
  onClick,
}: {
  selected: boolean;
  label: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        'flex flex-col items-start gap-1 rounded-lg border px-4 py-3 text-left transition',
        'hover:border-violet-500/40 hover:bg-card/60',
        selected
          ? 'border-violet-500/60 bg-violet-500/10 ring-1 ring-violet-500/40'
          : 'border-border/60 bg-card/30',
      )}
    >
      <span className="text-sm font-medium">{label}</span>
      <span className="text-xs text-muted-foreground">{hint}</span>
    </button>
  );
}
