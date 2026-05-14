'use client';

// Wait-state tutorial animation. Plays while POST /config/generate streams.
// Five chapters explain the bench's primitives (rail, roundtable, knowledge
// graph, worklog, reveal). Chapters cycle until generation completes;
// caption text under the animation comes from SSE `progress` events and
// updates independently of chapter timing.
//
// All SVGs are hand-coded paths animated with `motion`. Each chapter is
// self-contained so designers can swap in a Rive/Lottie file later
// without touching the wizard shell.

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';

const CHAPTERS = [
  {
    id: 'rail',
    title: 'Six surfaces, one bench',
    body: 'Advisor, Research, Drafts, Papers, Knowledge, Worklog — each one is opt-in.',
    durationMs: 4000,
    svg: <RailAnimation />,
  },
  {
    id: 'roundtable',
    title: 'A panel weighs in',
    body: 'Pick an advisor pool. Every reply is critiqued by 3–4 distinct lenses.',
    durationMs: 4500,
    svg: <RoundtableAnimation />,
  },
  {
    id: 'knowledge',
    title: 'Every insight becomes a node',
    body: 'Decisions, claims, hypotheses get extracted and linked into a graph.',
    durationMs: 4500,
    svg: <KnowledgeAnimation />,
  },
  {
    id: 'worklog',
    title: 'AI summarizes your progress',
    body: 'Weekly, monthly, quarterly. Sourced from activity + the knowledge graph.',
    durationMs: 4000,
    svg: <WorklogAnimation />,
  },
  {
    id: 'reveal',
    title: 'Almost ready',
    body: 'Picking your advisors, building your taxonomy, tuning prompts to your tone.',
    durationMs: 4000,
    svg: <RevealAnimation />,
  },
];

interface Props {
  caption: string;
}

export function WaitAnimation({ caption }: Props) {
  const [chapterIdx, setChapterIdx] = useState(0);

  useEffect(() => {
    const ch = CHAPTERS[chapterIdx];
    const t = setTimeout(() => {
      setChapterIdx((i) => (i + 1) % CHAPTERS.length);
    }, ch.durationMs);
    return () => clearTimeout(t);
  }, [chapterIdx]);

  const chapter = CHAPTERS[chapterIdx];

  return (
    <div className="flex flex-col items-center gap-8 w-full">
      <div className="relative h-56 w-full max-w-md flex items-center justify-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={chapter.id}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.04 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className="absolute inset-0 flex items-center justify-center"
          >
            {chapter.svg}
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="text-center space-y-2 max-w-md">
        <AnimatePresence mode="wait">
          <motion.div
            key={chapter.id + '-text'}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
          >
            <h2 className="text-lg font-semibold tracking-tight">
              {chapter.title}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {chapter.body}
            </p>
          </motion.div>
        </AnimatePresence>

        <div className="pt-4 h-6">
          <AnimatePresence mode="wait">
            {caption && (
              <motion.p
                key={caption}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.3 }}
                className="text-[11px] font-mono text-violet-300/80"
              >
                {caption}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Progress dots — purely decorative pacing cue */}
      <div className="flex items-center gap-1.5">
        {CHAPTERS.map((c, i) => (
          <span
            key={c.id}
            className={
              i === chapterIdx
                ? 'h-1.5 w-6 rounded-full bg-violet-400/80 transition-all'
                : 'h-1.5 w-1.5 rounded-full bg-muted-foreground/30 transition-all'
            }
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter SVGs — each ~200x200, paths/circles animated with motion
// ---------------------------------------------------------------------------

const ACCENTS = {
  violet: '#a78bfa',
  blue: '#60a5fa',
  orange: '#fb923c',
  teal: '#2dd4bf',
  emerald: '#34d399',
  rose: '#fb7185',
};

const RAIL_LETTERS = [
  { letter: 'R', color: ACCENTS.violet },
  { letter: 'A', color: ACCENTS.blue },
  { letter: 'D', color: ACCENTS.orange },
  { letter: 'P', color: ACCENTS.blue },
  { letter: 'K', color: ACCENTS.teal },
  { letter: 'W', color: ACCENTS.emerald },
];

function RailAnimation() {
  return (
    <svg width="220" height="220" viewBox="0 0 220 220" fill="none">
      <motion.rect
        x="10" y="20" width="40" height="180" rx="10"
        fill="rgba(124, 58, 237, 0.05)"
        stroke="rgba(124, 58, 237, 0.2)"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      />
      {RAIL_LETTERS.map((r, i) => (
        <motion.g
          key={r.letter}
          initial={{ opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15 + i * 0.25, duration: 0.4, ease: 'easeOut' }}
        >
          <rect
            x="18" y={32 + i * 28} width="24" height="24" rx="6"
            fill={r.color} fillOpacity="0.18"
            stroke={r.color} strokeOpacity="0.5"
          />
          <text
            x="30" y={48 + i * 28} textAnchor="middle"
            fontSize="13" fontWeight="600"
            fill={r.color} fillOpacity="0.95"
            fontFamily="ui-sans-serif, system-ui"
          >
            {r.letter}
          </text>
        </motion.g>
      ))}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.6, duration: 0.4 }}
      >
        <text
          x="80" y="115" fontSize="11" fill="rgba(229, 231, 235, 0.6)"
          fontFamily="ui-sans-serif, system-ui"
        >
          ← your rail
        </text>
      </motion.g>
    </svg>
  );
}

function RoundtableAnimation() {
  const advisors = [
    { angle: 0, color: ACCENTS.violet },
    { angle: 60, color: ACCENTS.blue },
    { angle: 120, color: ACCENTS.orange },
    { angle: 180, color: ACCENTS.teal },
    { angle: 240, color: ACCENTS.emerald },
    { angle: 300, color: ACCENTS.rose },
  ];
  const cx = 110, cy = 110, r = 60;
  return (
    <svg width="220" height="220" viewBox="0 0 220 220" fill="none">
      <motion.circle
        cx={cx} cy={cy} r="22"
        fill="rgba(124, 58, 237, 0.18)"
        stroke="rgba(124, 58, 237, 0.6)"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.4 }}
      />
      <motion.text
        x={cx} y={cy + 4} textAnchor="middle"
        fontSize="10" fill="rgba(229, 231, 235, 0.85)"
        fontFamily="ui-sans-serif, system-ui"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
      >
        Q?
      </motion.text>
      {advisors.map((a, i) => {
        const rad = (a.angle * Math.PI) / 180;
        const x = cx + r * Math.cos(rad);
        const y = cy + r * Math.sin(rad);
        return (
          <motion.g key={i}
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.4 + i * 0.12, duration: 0.4 }}
          >
            <circle cx={x} cy={y} r="16" fill={a.color} fillOpacity="0.18"
                    stroke={a.color} strokeOpacity="0.6" />
            <motion.line
              x1={cx + 22 * Math.cos(rad)} y1={cy + 22 * Math.sin(rad)}
              x2={x - 16 * Math.cos(rad)} y2={y - 16 * Math.sin(rad)}
              stroke={a.color} strokeOpacity="0.4" strokeWidth="1.5"
              strokeDasharray="3 3"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ delay: 0.5 + i * 0.12, duration: 0.5 }}
            />
          </motion.g>
        );
      })}
    </svg>
  );
}

function KnowledgeAnimation() {
  const nodes = [
    { x: 60, y: 60, label: 'decision', color: ACCENTS.emerald },
    { x: 160, y: 80, label: 'claim', color: ACCENTS.blue },
    { x: 90, y: 150, label: 'insight', color: ACCENTS.orange },
    { x: 170, y: 160, label: 'hypothesis', color: ACCENTS.violet },
  ];
  const edges = [
    [0, 1], [0, 2], [1, 3], [2, 3],
  ];
  return (
    <svg width="220" height="220" viewBox="0 0 220 220" fill="none">
      {edges.map(([a, b], i) => (
        <motion.line
          key={i}
          x1={nodes[a].x} y1={nodes[a].y}
          x2={nodes[b].x} y2={nodes[b].y}
          stroke="rgba(229, 231, 235, 0.35)"
          strokeWidth="1.5"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ delay: 0.6 + i * 0.2, duration: 0.5 }}
        />
      ))}
      {nodes.map((n, i) => (
        <motion.g key={i}
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.1 + i * 0.18, duration: 0.35, ease: 'backOut' }}
        >
          <circle cx={n.x} cy={n.y} r="18" fill={n.color} fillOpacity="0.2"
                  stroke={n.color} strokeOpacity="0.7" strokeWidth="1.5" />
          <text x={n.x} y={n.y + 32} textAnchor="middle"
                fontSize="9" fill={n.color}
                fontFamily="ui-sans-serif, system-ui">
            {n.label}
          </text>
        </motion.g>
      ))}
    </svg>
  );
}

function WorklogAnimation() {
  return (
    <svg width="220" height="220" viewBox="0 0 220 220" fill="none">
      <motion.line
        x1="20" y1="100" x2="200" y2="100"
        stroke="rgba(52, 211, 153, 0.35)" strokeWidth="2"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.6 }}
      />
      {[40, 80, 120, 160].map((x, i) => (
        <motion.circle
          key={x}
          cx={x} cy="100" r="4"
          fill={ACCENTS.emerald}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.4 + i * 0.15, duration: 0.3 }}
        />
      ))}
      <motion.g
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1.2, duration: 0.5 }}
      >
        <rect x="60" y="130" width="100" height="60" rx="6"
              fill="rgba(52, 211, 153, 0.1)"
              stroke="rgba(52, 211, 153, 0.5)" />
        <line x1="72" y1="145" x2="148" y2="145"
              stroke={ACCENTS.emerald} strokeOpacity="0.6" strokeWidth="2" />
        <line x1="72" y1="158" x2="135" y2="158"
              stroke={ACCENTS.emerald} strokeOpacity="0.4" strokeWidth="2" />
        <line x1="72" y1="171" x2="148" y2="171"
              stroke={ACCENTS.emerald} strokeOpacity="0.4" strokeWidth="2" />
      </motion.g>
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2, duration: 0.5 }}
      >
        <text x="20" y="92" fontSize="9" fill="rgba(229, 231, 235, 0.5)"
              fontFamily="ui-sans-serif, system-ui">Mon</text>
        <text x="180" y="92" fontSize="9" fill="rgba(229, 231, 235, 0.5)"
              fontFamily="ui-sans-serif, system-ui">Sun</text>
      </motion.g>
    </svg>
  );
}

function RevealAnimation() {
  return (
    <svg width="220" height="220" viewBox="0 0 220 220" fill="none">
      <motion.circle
        cx="110" cy="110" r="60"
        fill="none"
        stroke="rgba(167, 139, 250, 0.4)"
        strokeWidth="2"
        strokeDasharray="6 6"
        initial={{ rotate: 0, opacity: 0 }}
        animate={{ rotate: 360, opacity: 1 }}
        transition={{
          rotate: { repeat: Infinity, duration: 4, ease: 'linear' },
          opacity: { duration: 0.4 },
        }}
        style={{ transformOrigin: '110px 110px' }}
      />
      <motion.circle
        cx="110" cy="110" r="40"
        fill="rgba(167, 139, 250, 0.15)"
        stroke={ACCENTS.violet}
        strokeOpacity="0.5"
        initial={{ scale: 0 }}
        animate={{ scale: [0, 1.1, 1] }}
        transition={{ duration: 0.7, ease: 'easeOut' }}
      />
      <motion.path
        d="M 92 110 L 105 122 L 130 96"
        stroke={ACCENTS.violet}
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ delay: 0.7, duration: 0.5 }}
      />
    </svg>
  );
}
