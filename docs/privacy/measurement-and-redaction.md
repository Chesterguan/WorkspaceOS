# Measurement & Redaction — Egress Quantification + Placeholder Strategy

> Investigation doc. Companion to [`egress-audit.md`](./egress-audit.md).
> Defines (a) how to *measure* per-call data egress and (b) how to
> *redact* sensitive spans before egress using local-only placeholder
> substitution.
>
> **Last updated:** 2026-05-28
> **Status:** investigation — no code yet
> **Default redaction behaviour (decided 2026-05-28):** silent-replace
> with bench-TUI notification

## Problem statement

The audit in [`egress-audit.md`](./egress-audit.md) classifies *what
kinds of data* each call sends to the cloud, on a four-level
identifiability scale. That's a *qualitative* judgement. To talk
honestly with users we need two more things:

1. **Quantitative measurement.** For every cloud call: how many bytes
   did we send? Of those, how many bytes were each field (paper body
   vs venue context vs system prompt)? Without this we cannot answer
   "did anything leak today?" in a verifiable way.
2. **Mechanical redaction.** For generation tasks (paper writer, blog
   drafter, worklog) we can replace sensitive spans (experimental
   numbers, dataset names, proper nouns) with opaque placeholders
   before sending to cloud, then locally substitute the real values
   back into the response. Raw experimental data never leaves the
   machine.

This doc designs both. **Hardware / model picks for the redaction
detector are deferred** (see [`README.md`](./README.md#whats-not-here-yet-deliberate)).

---

## Part 1 — Measurement

### Goal

For every cloud egress site (16 sites listed in
[`egress-audit.md`](./egress-audit.md)), produce a structured record:

```json
{
  "ts": 1748448731.42,
  "call_id": "uuid",
  "surface": "paper",
  "service": "paper_service.generate_paper",
  "provider": "gemini",
  "model": "gemini-2.0-flash",
  "fields": {
    "paper_draft_body":     27418,
    "experimental_results":  6203,
    "venue_context":         3841,
    "system_prompt":         1024
  },
  "redaction": {
    "spans_replaced":      14,
    "bytes_replaced":     923,
    "categories":         { "metric": 6, "dataset": 3, "name": 5 }
  },
  "tokens_estimated": 9621,
  "user_id": "uuid",
  "project_id": "uuid"
}
```

Everything is **byte counts** of payload categories. No literal text
unless the user opts into the optional transcript log (L-3 in
[`known-leaks.md`](./known-leaks.md#l-3-no-prompt--response-transcript-is-persisted-anywhere)).

### Implementation primitives

| Primitive | Where it lives | What it does |
|---|---|---|
| `EgressRecorder` | new `app/services/egress_recorder.py` | Context manager. `with EgressRecorder(surface, service) as rec: rec.field("paper_body", text); ai.complete(system, rec.compose())` |
| `egress_logs` table | new Alembic migration | Persistent storage of the structured records above |
| `/api/v1/egress/recent` | new router | Bench UI reads this to render the "what went out today" view |
| TUI emit | extend `event_stream.emit` | Each cloud call emits a `data.egress` event with the summary |

### What we get once instrumented

- **Per-day / per-surface / per-project byte counts.** "Today this
  workspace sent 142 KB to Gemini, of which 87 KB was paper body and
  41 KB was advisor chat history."
- **Verifiable claim test.** "Strict mode promises no draft content
  leaves the machine." Click into the egress log; if the surface's
  byte count is zero, the promise held.
- **Regression detection.** A new feature accidentally doubles
  outbound traffic → it shows up in the per-day plot.

### What we don't get

- **Literal payloads.** We deliberately store byte counts, not strings.
  Storing prompts is a separate opt-in feature (L-3). The user's
  audit story is "I trust the byte counts and the redaction
  detector," not "I can read every byte that left."

### Storage cost

Per call ~250 bytes structured JSON, ~50 calls/day for a daily-driver
user ≈ 12 KB/day, ~4 MB/year. Negligible.

---

## Part 2 — Redaction

Two complementary strategies. **Tag-based redaction is the primary
mechanism** because it's user-controlled, deterministic, and trivial
to verify. **Span-based redaction is a refinement** for free-form
text (chat messages, prompts the user types live) where there is no
file to tag.

### Part 2A — Tag-based file/entry redaction (primary)

#### Premise

`MemoryEntry.metadata_` is JSONB and already stores a `tags` list
(populated by `file_ingest_service.ingest_file` and the manual tag
merger). We reserve a `privacy:*` tag namespace to drive cloud-egress
policy. The user (or an auto-tag heuristic) marks a file or memory
entry as private once; from then on, **every** cloud call that would
have included that content substitutes a placeholder instead.

This solves the user's case directly: tag the experimental-results
file as `privacy:local-only`, and even though the paper writer still
calls Gemini, the raw results never leave the machine. The cloud
model sees that there *is* an experimental results artifact (by
reference) but never its contents.

#### Reserved tag namespace

| Tag | Policy when assembled into a cloud prompt |
|---|---|
| `privacy:local-only` | Replaced with a stub: `[private — {entry_type} — {summary or filename} — not sent to cloud]`. Cloud sees the existence and shape of the artifact but no contents |
| `privacy:redact-content` | Schema + first-line preserved; body redacted. For structured artifacts where the shape is non-sensitive but the values are |
| `privacy:redact-values` | (Tabular data) Column headers and row count sent; cell values replaced with `[v_1]` etc. mapped back locally |
| `privacy:public` | Explicit opt-in — content can leave the machine in full. Used to override a project-level default |
| *(unset)* | Default policy applies. See **defaults** below |

#### Default policy

A project carries a `privacy_default` setting: `open` (current behaviour
— content goes verbatim) or `strict` (untagged entries treated as
`privacy:redact-content`). New projects opt in via the Settings panel;
the demo / out-of-box project stays `open`.

#### Per-entry data flow

```
[user clicks Generate Paper]
        │
        ▼
┌──────────────────────────────────────────┐
│ assemble project context                 │
│   - list relevant memory entries         │
│   - for each entry: resolve privacy tag  │
│     (entry tag → project default)        │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│ build cloud prompt with stubs:           │
│                                          │
│   "Methods reference:                     │
│    [private — file — results-Q1.xlsx —   │
│     12 rows × 8 cols (sample, treatment, │
│     mean, std, p_value, ...) —           │
│     not sent to cloud]                    │
│                                          │
│    Discussion needs to narrate that      │
│    this artifact exists and was the      │
│    source of the headline result."        │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│ cloud (Gemini) writes prose that         │
│ references the artifact by stub.         │
│ User reviews the draft locally and       │
│ fills the actual numbers in by hand —    │
│ or runs a local model pass that          │
│ substitutes the cells.                    │
└──────────────────────────────────────────┘
```

The key property: **nothing the cloud model sees lets it reconstruct
the experimental data**. The user gets paper-quality prose framing
around a placeholder they fill in privately.

#### What gets included in the stub

For a `privacy:local-only` entry, the stub carries the minimum the
cloud needs to write coherently:

- entry type (file / draft / note / commit-summary)
- short hint (filename, draft title, or first 80 chars of summary)
- structural shape if obvious (row × col count for tables, page count
  for PDFs, # of sections for drafts)
- `not sent to cloud` literal marker so the model knows not to invent

For a `privacy:redact-content` entry the body is dropped but tags,
title, and entry_type remain.

For a `privacy:redact-values` entry (tables, structured data) the
schema stays and each cell becomes a placeholder.

#### Where tags propagate

- **File ingest** — when a file is tagged, every memory entry derived
  from that file inherits the tag (chunked entries share the parent's
  tags).
- **Manual annotations** — entries created via the `/memory/annotate`
  endpoint inherit the active project's default tag.
- **Chat extraction** (`knowledge_extractor`) — extracted nodes
  inherit privacy tags from the chat message's source project.
- **Wiki summary** (`memory_service.update_wiki_summary`) — assembled
  context filters out `privacy:local-only` entries entirely before
  building the prompt; the wiki page itself inherits the most
  restrictive tag present in its inputs.

#### Why this is the primary mechanism

| Property | Tag-based | Span-based |
|---|---|---|
| User-controlled | ✅ explicit | ❌ depends on detector |
| Deterministic | ✅ exact | ⚠️ false neg / false pos |
| Auditable | ✅ "this entry tagged X" | ⚠️ "the detector replaced N spans" |
| Verifiable in test | ✅ unit-test the assembler | ⚠️ requires golden detector eval |
| Implementation cost | ✅ low — `MemoryEntry.metadata_` already exists | ⚠️ NER detector + glossary + post-hoc verify |
| Handles free-form chat input | ❌ no — user typed it just now | ✅ yes |

Tag-based covers most surfaces; span-based fills the chat gap.

---

### Part 2B — Span-based redaction (supplementary)

For surfaces where the user's content is typed live and doesn't sit
in a file (cofounder chat, research roundtable, the wizard's free-form
answers), tagging doesn't apply. Span-based redaction is the fallback:

#### Detection cascade

| Category | Detection | Examples | Notes |
|---|---|---|---|
| **Numerics** | regex, deterministic | `87.3%`, `p < 0.001`, `n = 1,247`, `2.4 mg/mL` | Cheap, high precision. Risk: dropping all numbers makes some prompts incoherent — only redact in result/metric context |
| **Identifiers** | regex, deterministic | email, file path, URL, UUID, IP | Cheap |
| **Glossary** | exact string match | user-curated list ("Project Phoenix" → `[CODENAME_1]`) | User-controlled. The strongest privacy signal because the user opts in explicitly. **Shared with tag-based: any string in a `privacy:*` tagged entry auto-joins the glossary** |
| **Named entities** | local-LLM NER | people, orgs, dataset names, gene IDs, compound names | Higher cost, higher recall. Needs a competent local model |
| **Free-form spans** | local-LLM span tagging | "redact the experiment description" | Highest cost. Optional — only enabled for high-stakes surfaces |

#### Glossary sharing with tag-based

The glossary lookup is automatically populated from every
`privacy:*` tagged entry's named values. If the user tagged a
results file containing "scribe-v3" as `privacy:local-only`, then
the next time the user types "scribe-v3" into the cofounder chat,
span-based redaction catches it via glossary match. **Tag-based
redaction strengthens span-based redaction** — the more files the
user marks private, the more reliable the chat-time detection
becomes.

### Per-egress applicability (extends `egress-audit.md`)

| EG ref | Surface | Redactable? | Reason |
|---|---|---|---|
| EG-01 | classifier | ❌ Useless | Whole content is the input — redact → nothing to classify. Better fix: move to local (capability matrix already says 🟢) |
| EG-02 | file_ingest auto-tag | ❌ Useless | Same as above |
| EG-03 | knowledge extractor | ❌ Useless | Same — extractor's job is to find structure in the content |
| EG-04 | worklog | ✅ Yes | Narrates metrics around numbers — placeholders preserve narrative |
| EG-05 | wiki summary | ⚠️ Partial | Summary needs facts; redaction would hollow it. Move to local instead |
| EG-06 | blog drafts | ✅ Yes | Prose around facts |
| EG-07 | agentic generation | ✅ Yes (writer step) / ⚠️ partial (reviewer step) | Writer can use placeholders; reviewer needs unredacted content to critique |
| EG-08 | methods drafter | ⚠️ Partial | Methodology has to be present for reviewers; redaction would degrade |
| EG-09 | advisor chat | ✅ Mostly | Names + project identifiers redactable; user's *claims* often need to stay for the advisor to give useful advice |
| EG-10 | research roundtable | ❌ No | Reviewers' job is to judge the claims. Redacting → generic feedback |
| EG-11 | paper writer | ✅ **Yes — the primary use case** | The user-cited use case: methods / results have placeholders, cloud writes framing |
| EG-12 | paper reviewers | ❌ No | Same as EG-10 |
| EG-13 | wizard config gen | ⚠️ Partial | Domain answer must be present; specific advisor names redactable |
| EG-14 | knowledge query embed | n/a | Should be local (L-1); redaction moot |
| EG-15 | feedback (GitHub) | ✅ Yes | Auto-context block can have project_id / user_id redacted before submit |
| EG-16 | publish | ❌ n/a | Explicit user action; content is meant to be public |

**Net redactability across the 16 sites:**

- **5 sites are good fits** for redaction (worklog, blog, agentic writer, paper writer, feedback)
- **6 sites are not** (classifier/extractor/auto-tag/wiki: redaction is useless because the content *is* the input → move to local instead; research/paper reviewers and methods: reviewers need unredacted content for genuine critique)
- **3 sites are partial** (advisor chat, wizard, agentic reviewer step)
- **2 sites are not applicable** (knowledge embed should be local; publish is explicit)

### Worked example — paper introduction generation (tag-based)

**User's workspace:**

```
Project "Scribe v4"
├── results-Q1-2026.xlsx       (tag: privacy:local-only)
├── methods-draft.md            (tag: privacy:redact-content)
├── related-work-notes.md       (no tag)
└── memory entries: 47 (12 inherited privacy:local-only from results-Q1-2026.xlsx)
```

**User clicks "Generate Paper → Introduction".** Paper service
assembles project context. The privacy-tag assembler runs over every
candidate context entry:

```
results-Q1-2026.xlsx     → privacy:local-only      → stub
methods-draft.md         → privacy:redact-content  → title + headers only
related-work-notes.md    → (default open)          → full content
```

**Prompt actually sent to Gemini:**

> ## Project context
>
> [private — file — `results-Q1-2026.xlsx` — XLSX, 1 sheet,
>  12 rows × 8 cols (sample, treatment, mean, std, p_value,
>  effect_size, n, notes) — not sent to cloud]
>
> [partial — draft — `methods-draft.md` — section headers:
>  1. Pre-training corpus 2. Training regime 3. Evaluation
>  4. Statistical analysis — body redacted]
>
> [full content of related-work-notes.md follows...]
>
> ---
>
> Write the Introduction section for a paper presenting this
> work. Reference the artifacts above by name; do not invent
> details about redacted content.

**Gemini response:**

> Recent advances in language-model pre-training have raised the
> ceiling on multi-task generalisation, yet domain-specific
> applications remain bottlenecked by the quality of curated
> in-domain corpora. The present work extends this line through
> a focused training regime — detailed in §Methods — evaluated
> against the experimental protocol summarised in
> `results-Q1-2026.xlsx`. The headline finding is reported in
> §Results; we situate it here against the lineage of in-house
> baselines reviewed in §Related Work...

**User rehydrates locally:**
- Opens the draft in the editor.
- The `results-Q1-2026.xlsx` reference is preserved verbatim — they
  fill in the actual metric numbers themselves, in the editor, never
  through a cloud round-trip.
- Optionally a local model pass reads the XLSX and substitutes the
  cells into the draft.

**What Gemini saw:** the prose framing of the work, the existence of
a results file with that schema, the methods chapter headers, all of
the related-work notes. **What it never saw:** any cell in the
results file, any sentence of the methods body, any number, any
author name. **What we measured:** 1 file stubbed (8 KB original, 412
bytes stub), 1 entry partially redacted (3.2 KB → 178 bytes), 1 entry
verbatim. Egress total ~4.1 KB instead of ~11 KB.

### Worked example — span-based fallback (cofounder chat)

When the user types into the R surface, there's no file to tag. The
span-based cascade fires:

> **User types:** "We're seeing ~87% retention on the v4 pilot with
> Acme Corp — should I be worried about churn at the v5 launch?"
>
> **Glossary catches:** `Acme Corp` is in the user's glossary
> (auto-added because a file tagged `privacy:local-only` contained
> the string).
>
> **Regex catches:** `87%` matches the numeric-with-context rule.
>
> **Redacted prompt to Gemini:**
> "We're seeing [METRIC_1] retention on the v4 pilot with
>  [GLOSSARY_1] — should I be worried about churn at the v5 launch?"
>
> **Advisor reply uses placeholders, which are rehydrated locally
> before the user sees the response.**

### Failure modes — be honest about these

1. **User forgets to tag a sensitive file.** The default-policy knob
   exists for this: `privacy_default: strict` at the project level
   means untagged entries are still treated as `redact-content`.
   Mitigation: ingest-time prompt — "this file looks like results
   data; tag as private?" based on filename heuristics
   (`results*.xlsx`, `data*.csv`, etc.) and content sniffing.
2. **Model drops placeholders.** Some cloud models paraphrase tokens
   ("the private file" → "the data file"). Mitigation: system prompt
   explicitly says "preserve [BRACKETED] tokens and `[private — …]`
   stubs verbatim"; post-hoc verification checks every stub appears
   unmodified in the response; if any are missing, retry once and
   fall back to local generation.
3. **Span-based false negatives.** A novel compound name not in the
   glossary and not caught by NER → leaks. Mitigation: glossary
   inheritance from tagged files is the safety net; per-call
   redaction summary is shown in the TUI so the user can audit.
4. **Over-aggressive redaction.** Span-based detection sometimes
   redacts so much that the prompt becomes incoherent ("we used the
   [DATASET_1] benchmark for the [DATASET_2] experiment"). Tag-based
   is immune to this because stubs are bounded per entry; only
   span-based has the failure mode. Mitigation: per-category
   thresholds; user can disable over-aggressive categories.
5. **Reviewer-style surfaces cannot be redacted.** Paper reviewers
   exist to challenge the experimental claims. Redacting →
   reviewer gives generic feedback. **Honest UX:** these surfaces
   show an explicit "send unredacted" gate before each run, or
   collapse to a local-only reviewer (quality drop documented). Tag
   policy still applies — a `privacy:local-only` artifact never
   reaches a reviewer call; the surface degrades to local reviewer
   for that project.

### Default behaviour

Decided 2026-05-28: **silent replace**. Tag-stubs and detected spans
replaced automatically before egress. Bench TUI emits one event per
call:

```
data.egress  paper.generate_paper → gemini
             2 entries stubbed (privacy:local-only)
             1 entry partially redacted (privacy:redact-content)
             3 spans replaced (glossary + numeric)
             4.1 KB sent (down from 11.0 KB raw)
```

User can click the event to inspect the redaction map. First-class
settings: privacy tag editor on every memory entry, per-category
enable/disable for span-based, glossary editor, "redaction
verification failed" alerts.

---

## Open questions (defer to design phase)

1. **Where does the redaction detector run?** Same Ollama instance as
   embeddings, or a separate quantised NER model? — *defer to model
   recommendations doc once we measure.*
2. **What's the glossary UX?** Settings page with free-text add, or
   inline-from-content ("right-click → always redact 'Project Phoenix'
   in cloud calls")? — *defer to UX brainstorm.*
3. **How do we surface the egress log?** New surface, extension to
   the existing TUI panel, or both? — *defer to bench-UI iteration.*
4. **What's the threshold for "too much was redacted"?** Above some
   ratio (e.g., 40% of payload bytes replaced), prompt the user to
   consider running the surface locally instead. — *needs measured
   data; defer.*
