'use client';

// Top-level wizard shell. Manages step state, calls /config/generate as
// SSE during the wait phase, then shows PreviewPane. Apply writes the
// config and routes to /bench.

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AnimatePresence, motion } from 'motion/react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  AdvisorStep,
  AudienceStep,
  CadenceStep,
  DomainStep,
  OutputsStep,
  StageStep,
  TrackedStep,
} from './steps';
import { WaitAnimation } from './WaitAnimation';
import { PreviewPane } from './PreviewPane';
import {
  applyConfig,
  fetchOnboardingState,
  generateConfig,
  type GenerateController,
} from '@/lib/onboarding/api';
import type { GeneratedConfig, OnboardingAnswers } from '@/lib/onboarding/types';

type Phase = 'questions' | 'waiting' | 'preview' | 'error';

const STEPS = [
  DomainStep,
  OutputsStep,
  AudienceStep,
  AdvisorStep,
  TrackedStep,
  CadenceStep,
  StageStep,
] as const;

const EMPTY_ANSWERS: OnboardingAnswers = {
  domain: '',
  primary_outputs: [],
  audience: [],
  advisor_panel: null,
  tracked_artifacts: null,
  cadence: null,
  stage: null,
};

export function Wizard() {
  const router = useRouter();

  const [answers, setAnswers] = useState<OnboardingAnswers>(EMPTY_ANSWERS);
  const [stepIdx, setStepIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>('questions');
  const [direction, setDirection] = useState<1 | -1>(1);

  const [caption, setCaption] = useState<string>('');
  const [config, setConfig] = useState<GeneratedConfig | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [applying, setApplying] = useState(false);

  const generationRef = useRef<GenerateController | null>(null);

  // Prefill from saved answers if the user is re-running
  useEffect(() => {
    let cancelled = false;
    fetchOnboardingState()
      .then((state) => {
        if (!cancelled && state.onboarding_answers) {
          setAnswers({ ...EMPTY_ANSWERS, ...state.onboarding_answers });
        }
      })
      .catch(() => { /* unauth or fresh user — fine */ });
    return () => { cancelled = true; };
  }, []);

  const StepComponent = STEPS[stepIdx];
  const isLast = stepIdx === STEPS.length - 1;
  const canAdvance = stepIdx === 0 ? answers.domain.trim().length > 0 : true;

  function patch(p: Partial<OnboardingAnswers>) {
    setAnswers((a) => ({ ...a, ...p }));
  }

  function next() {
    if (!canAdvance) return;
    if (isLast) {
      startGeneration();
    } else {
      setDirection(1);
      setStepIdx((i) => i + 1);
    }
  }

  function back() {
    if (stepIdx === 0) return;
    setDirection(-1);
    setStepIdx((i) => i - 1);
  }

  function startGeneration() {
    setPhase('waiting');
    setCaption('');
    setConfig(null);
    setErrorMsg('');

    generationRef.current?.abort();
    generationRef.current = generateConfig(answers, {
      onProgress: (c) => setCaption(c),
      onDone: (cfg) => {
        setConfig(cfg);
        setPhase('preview');
      },
      onError: (msg) => {
        setErrorMsg(msg);
        setPhase('error');
      },
    });
  }

  async function handleApply() {
    if (!config) return;
    setApplying(true);
    try {
      await applyConfig(config.raw_files);
      toast.success('Workbench configured. Welcome.');
      router.push('/bench');
    } catch (e) {
      toast.error('Apply failed — please try again.');
      setApplying(false);
    }
  }

  // Cleanup pending SSE on unmount
  useEffect(() => () => generationRef.current?.abort(), []);

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border/40">
        <div className="text-sm font-semibold tracking-tight">WorkspaceOS</div>
        {phase === 'questions' && (
          <button
            onClick={() => router.push('/bench')}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip for now →
          </button>
        )}
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-10">
        <AnimatePresence mode="wait">
          {phase === 'questions' && (
            <motion.div
              key={`q-${stepIdx}`}
              custom={direction}
              variants={questionVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.35, ease: 'easeOut' }}
              className="w-full"
            >
              <StepComponent
                answers={answers}
                onChange={patch}
                onNext={next}
              />
            </motion.div>
          )}

          {phase === 'waiting' && (
            <motion.div
              key="wait"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              className="w-full"
            >
              <WaitAnimation caption={caption} />
            </motion.div>
          )}

          {phase === 'preview' && config && (
            <motion.div
              key="preview"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              className="w-full"
            >
              <PreviewPane
                config={config}
                applying={applying}
                onApply={handleApply}
                onRegenerate={startGeneration}
              />
            </motion.div>
          )}

          {phase === 'error' && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="w-full max-w-md mx-auto text-center space-y-4"
            >
              <h1 className="text-xl font-semibold">{friendlyError(errorMsg).title}</h1>
              <p className="text-sm text-muted-foreground">
                {friendlyError(errorMsg).message}
              </p>
              <div className="flex items-center justify-center gap-3">
                <Button onClick={startGeneration}>Try again</Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    // Land back on the FIRST question, not wherever the
                    // user happened to be. The most common fixable
                    // error is the domain answer itself; dumping them
                    // on the last step (stage hint) just confused
                    // people in the cold-open test.
                    setStepIdx(0);
                    setDirection(-1);
                    setPhase('questions');
                  }}
                >
                  Edit answers
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer nav — only during questions */}
      {phase === 'questions' && (
        <footer className="border-t border-border/40 px-6 py-4 flex items-center justify-between max-w-4xl w-full mx-auto">
          <Button
            variant="ghost"
            onClick={back}
            disabled={stepIdx === 0}
            className="text-muted-foreground"
          >
            Back
          </Button>
          <ProgressDots count={STEPS.length} active={stepIdx} />
          <Button onClick={next} disabled={!canAdvance}>
            {isLast ? 'Generate my workbench' : 'Next →'}
          </Button>
        </footer>
      )}
    </div>
  );
}

// Turn a raw backend error string into something a non-developer can
// act on. The cold-open test surfaced a raw
// `generate 422: {"detail":[{"type":"string_too_long",...}]}` dump on
// the "Something went wrong" screen — meaningless to the target user.
function friendlyError(raw: string): { title: string; message: string } {
  const r = (raw || '').toLowerCase();
  if (r.includes('string_too_long') || r.includes('at most 1000')) {
    return {
      title: 'That answer is a little long',
      message:
        'Your field description is over the limit. Click "Edit answers" and trim the first question to a sentence or two.',
    };
  }
  if (r.includes('string_too_short') || r.includes('at least 1')) {
    return {
      title: 'One question needs an answer',
      message:
        'The first question (what field are you in) can\'t be empty. Click "Edit answers" to fill it in.',
    };
  }
  if (r.includes('api key') || r.includes('api_key') || r.includes('invalid_argument')) {
    return {
      title: 'AI provider not reachable',
      message:
        'The workbench generator couldn\'t reach the AI provider. Check your AI key in Settings → AI & API Keys, then try again.',
    };
  }
  if (r.includes('timeout') || r.includes('timed out')) {
    return {
      title: 'That took too long',
      message: 'The generator timed out. Try again — it usually works on a second attempt.',
    };
  }
  return {
    title: 'Something went wrong',
    message:
      'The workbench generator hit an error. Try again, or edit your answers and retry. ' +
      (raw ? `(Details: ${raw.slice(0, 160)})` : ''),
  };
}

const questionVariants = {
  enter: (direction: number) => ({ opacity: 0, x: direction > 0 ? 24 : -24 }),
  center: { opacity: 1, x: 0 },
  exit: (direction: number) => ({ opacity: 0, x: direction > 0 ? -24 : 24 }),
};

function ProgressDots({ count, active }: { count: number; active: number }) {
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: count }).map((_, i) => (
        <span
          key={i}
          className={
            i === active
              ? 'h-1.5 w-5 rounded-full bg-violet-400/80 transition-all'
              : i < active
                ? 'h-1.5 w-1.5 rounded-full bg-violet-400/40 transition-all'
                : 'h-1.5 w-1.5 rounded-full bg-muted-foreground/30 transition-all'
          }
        />
      ))}
    </div>
  );
}
