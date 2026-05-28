# Privacy Prototype — Design

**Date:** 2026-05-28
**Status:** Draft (brainstorming) — pending user review
**Author:** chesterguan + Claude

## Summary

Land a working privacy prototype for WorkspaceOS that holds up to a
fresh non-CS user opening a new project, ingesting files, marking
some as private, and generating content end-to-end. The user can
look at the bench TUI and prove, byte-by-byte, what data left the
machine. Cloud-quality generation still works — the cloud just
receives stubs instead of the private content.

This is **not** a public release. It's the internal prototype that
makes the privacy claims real enough to demo to a non-CS user and have
them believe it.

Investigation rationale lives in [`docs/privacy/`](../../privacy/);
this doc is the design that builds on it.

## Goals

- **Verifiable.** Every cloud call leaves a structured record of what
  fields went out (byte-count level). User can open the bench and
  audit any call.
- **Tag-controlled.** A file (or whole project) marked
  `privacy:local-only` never has its content reach the cloud, on any
  surface, no matter which generation feature the user triggers.
- **Cloud-quality preserved where possible.** The paper writer,
  blog drafter, worklog, and cofounder advisor all continue to use
  Gemini. They receive stubs in place of tagged content and produce
  prose around the stubs.
- **End-to-end validation flow works.** A non-CS user can create a
  new project, drop a folder of files, tag results-style files as
  private, generate a paper introduction, and inspect the egress log
  to confirm.
- **No standard dropped.** Tests + code-review subagent + manual e2e
  + perf check per workstream (see [Standards](#standards)).

## Non-goals (v1)

- Public release / changelog / migration notes.
- Cloud-LLM diversity for paper reviewers — the multi-provider
  paper-reviewer roundtable stays as-is; in privacy mode it gates
  on explicit user override or downgrades to local reviewer.
- Local-model recommendations or hardware tiers — both explicitly
  deferred (see [`docs/privacy/README.md`](../../privacy/README.md)).
- Transcript persistence (full prompt + response log) — opt-in
  feature deferred to a later release. v1 stores byte-count
  breakdowns only.
- GitHub-as-private-storage backend — parked.
- Feedback button rework — parked until non-CS onboarding for GitHub
  is figured out separately.
- Wizard / onboarding rework — the existing wizard stays; new
  projects pick up privacy defaults from a Settings panel.

## Decisions register

Consolidated from the 2026-05-28 brainstorming session.

| Decision | Choice |
|---|---|
| Default privacy mode for fresh installs | **Balanced** — cloud-required features work but require explicit one-time confirm per surface; cloud-optional features stay local by default |
| Redaction default behaviour | **Silent replace** — tag-stubs and detected spans replaced automatically; TUI emits one event per call |
| Primary redaction strategy | **Tag-based** on `MemoryEntry.metadata_["tags"]` with reserved `privacy:*` namespace |
| Supplementary redaction | **Span-based** (regex + glossary + local-NER) for chat-time free-form text where there is no file to tag |
| File ingest scope this week | Local folder watcher + LiteParse swap. **Google Drive deferred** |
| Feedback function | **Deferred** until non-CS GitHub onboarding is figured out separately |
| GitHub-as-private-storage | **Parked** — interesting v0.4+ idea; not this scope |
| Execution mode | Worktrees per workstream + code-reviewer subagent gate before merge |

## Standards

Every workstream must satisfy all four before it is marked done:

1. **Tests.** Unit + integration tests covering happy path and
   obvious failure modes. Privacy claims must be testable —
   e.g., "the tag assembler was given an entry with
   `privacy:local-only`; verify the assembled prompt contains the
   stub and never contains the entry content."
2. **Code-review subagent pass.** Each workstream gets reviewed by a
   separate `code-reviewer` subagent before merge.
3. **Manual end-to-end validation.** The bench comes up in Docker;
   feature exercised in the browser; behaviour matches the spec.
4. **Performance bar.** Tag assembler, `record_egress`, and span
   detection all run on the hot path. Each must add **< 50 ms** to
   the surfaces it touches. If a workstream can't hit the bar, it
   ships gated behind a Settings toggle, not enabled by default.

## Architecture (concise)

```
                          ┌─────────────────────────────────┐
                          │  Settings UI (Privacy panel)   │
                          │   - mode: Balanced / Strict     │
                          │   - per-project default tag     │
                          │   - glossary editor             │
                          │   - watched folders             │
                          └────────────┬────────────────────┘
                                       │ writes
                                       ▼
                          ┌─────────────────────────────────┐
                          │  Existing storage, no new table:│
                          │  - MemoryEntry.metadata_.tags   │
                          │    (JSONB, already in use)      │
                          │  - Project.privacy_default      │
                          │    (new column, Alembic)        │
                          │  - User glossary list           │
                          │    (added to settings model)    │
                          └─────────────────────────────────┘
                                       ▲                ▲
            ┌──────────────────────────┘                │
            │                                            │
┌───────────┴─────────────┐         ┌──────────────────┴───────────────┐
│  Folder watcher          │         │  Tag-resolving prompt assembler  │
│  (host bridge)           │         │  - given List[MemoryEntry]       │
│  - LiteParse for PDF/    │  ──▶    │  - looks up effective tag        │
│    DOCX/XLSX/PPTX        │         │  - emits stub or content         │
│  - auto-tag heuristic    │         │  - returns assembled string +    │
│  - drops into local-     │         │    redaction summary             │
│    ingest pipeline       │         └────────────────┬─────────────────┘
└──────────────────────────┘                          │
                                                       │ used by
                                                       ▼
                       ┌───────────────────────────────────────────────┐
                       │  paper_service / blog_service / worklog /     │
                       │  chat_service / advisors / etc.               │
                       │  (wrap their existing prompt construction     │
                       │   with the assembler)                          │
                       └─────────────────────────┬─────────────────────┘
                                                  │ every cloud call
                                                  ▼
                       ┌───────────────────────────────────────────────┐
                       │  EgressRecorder (context manager)             │
                       │  - field("paper_body", text)                  │
                       │  - field("methods_stub", stub)                │
                       │  - records to egress_logs table               │
                       │  - emits "data.egress" event to TUI           │
                       └───────────────────────────────────────────────┘
                                                  │
                                                  ▼
                       ┌───────────────────────────────────────────────┐
                       │  Bench TUI panel                              │
                       │  - per-call event with byte breakdown         │
                       │  - click → redaction map for that call        │
                       │  - per-project daily egress summary           │
                       └───────────────────────────────────────────────┘
```

## Workstreams (10)

Each workstream is one merge unit. `dep:` lists must complete first.
Items without a `dep:` can start immediately.

### Foundation (sequential — these block everything else)

#### W1 — Fix L-1 and L-2 leaks
- L-1: `knowledge_service.query_embedding` → use `get_local_client()`;
  re-embed existing knowledge nodes with the local model in a one-off
  migration script.
- L-2: remove direct `OpenAIClient()` from `agents.py`,
  `agentic_generation.py`. For `paper_reviewers.py` and
  `paper_service.py`, gate behind a new `paper_reviewer_providers`
  setting; explicit egress reason in the TUI event.
- Tests: unit-test each fixed call; integration test that
  `CLOUD_AI_PROVIDER=ollama` actually keeps traffic local.
- **No deps. Independent of the rest. Land first to derisk.**

#### W2 — `record_egress` instrumentation
- New table `egress_logs` (Alembic migration) with the schema from
  [`measurement-and-redaction.md` § Part 1](../../privacy/measurement-and-redaction.md#implementation-primitives).
- New `app/services/egress_recorder.py` providing `EgressRecorder`
  context manager.
- Wrap every cloud call in the 16 sites listed in
  [`egress-audit.md`](../../privacy/egress-audit.md).
- New router `GET /api/v1/egress/recent` for the TUI.
- TUI emit: `data.egress` event per cloud call.
- Tests: each wrapped site records its expected field breakdown.
- **dep:** W1 (so we're not instrumenting buggy callers)

#### W3 — `privacy:*` tag namespace + project default
- Reserve `privacy:local-only | redact-content | redact-values | public`
  as recognised values in `MemoryEntry.metadata_["tags"]`.
- New column `Project.privacy_default` (Alembic) — `open | strict`.
- New router endpoints to read/write entry tags and project default.
- Tag inheritance: file → derived memory entries; chat → extracted
  knowledge nodes.
- Tests: tag propagation across ingest + extraction paths.
- **dep:** none (purely additive)

#### W4 — Tag-resolving prompt assembler
- New `app/services/privacy_assembler.py`:
  ```python
  def assemble_context(
      entries: List[MemoryEntry],
      project: Project,
  ) -> Tuple[str, RedactionSummary]:
      ...
  ```
- Stub formats per [§ Part 2A](../../privacy/measurement-and-redaction.md#what-gets-included-in-the-stub).
- Hooks `EgressRecorder.redaction_summary` so byte counts flow.
- Tests: every tag value produces the right stub; mixed-tag inputs
  produce the right composite output; no tagged-content bytes appear
  in the assembled string.
- **dep:** W3

### Generation integrations (parallel after foundation)

#### W5 — Paper writer integration (lead use case)
- `paper_service.generate_paper` calls `assemble_context` for its
  context block.
- Paper-reviewer surface gate: if any context entry resolves to
  `privacy:local-only`, the reviewer pass refuses to run and surfaces
  a modal — "*N entries in this project are marked private. The
  cloud reviewer roundtable will see the entire paper draft. Choose:
  skip review, or send unredacted this run.*" No third "downgrade to
  local reviewer" option this week — that's a v2 polish.
- Tests: end-to-end on a project with a tagged results file.
- **dep:** W2, W4

#### W6 — Blog / worklog / wiki integration
- Same wrapping pattern for `blog_service`, `worklog_service`,
  `memory_service.update_wiki_summary`.
- Tests: each surface assembles context through the assembler.
- **dep:** W2, W4

#### W7 — Chat surfaces + span-based redaction
- `chat_service` (cofounder R) and `research_service` (research A)
  use the assembler for memory context.
- Live user-typed messages run through the span-based detector:
  regex pass (numerics, emails, URLs, file paths) + glossary pass.
- Glossary auto-populates from `privacy:*` tagged entries (see
  [§ Glossary sharing](../../privacy/measurement-and-redaction.md#glossary-sharing-with-tag-based)).
- **Local-NER pass is out of scope for v1** — would need a model
  eval pass we haven't run. The regex + glossary cascade is the
  v1 detector; NER is a v2 improvement.
- Tests: span detection precision on a handcrafted set covering the
  regex categories; integration test that a string from a
  `privacy:local-only` file is redacted when typed into chat.
- **dep:** W2, W4

### Ingest + UX (parallel after foundation)

#### W8 — Local folder watcher + LiteParse
- Settings: watched-paths list. Host-side bridge (extends
  `local_ingest_service` pattern) tails the paths via FS events,
  parses via LiteParse, calls into `ingest_file`.
- Replace PyPDF2 in `file_ingest_service._extract_text` with
  LiteParse Python binding.
- Auto-tag heuristic for results-like filenames (`*results*`,
  `*data*.xlsx`, `*raw*.csv`) — suggest `privacy:local-only` at
  ingest time; user confirms or rejects.
- Tests: watcher dedups via content hash; LiteParse output verified
  against PyPDF2 baseline on a corpus; heuristic precision/recall
  measured on real filenames.
- **dep:** W3 (for the auto-tag heuristic to write `privacy:*` tags)

#### W9 — Settings UI for privacy + tags + glossary
- New `/settings/privacy` panel: mode toggle, project-default
  picker, glossary editor, watched-folder list.
- Per-entry tag editor on the Memory / Files list — small chip
  with the active tag, click to change.
- Tests: e2e via Playwright on the validation project flow.
- **dep:** W3, W7, W8 (it's the UI surface for all of them)

#### W10 — Bench egress panel + click-to-inspect
- Extend the existing `AgentLogPanel` (the right-rail TUI) with a
  per-event byte-breakdown pill for `data.egress` events.
- Click an egress event → modal with the redaction map for that
  call (which entries were stubbed, what categories of spans were
  replaced, total bytes sent vs raw).
- New tile on the bench: today's per-project egress totals with a
  filter chip per surface.
- Tests: e2e — generate a paper, confirm the panel shows the right
  call with the right stub count.
- **dep:** W2, W4

## Dependency DAG

```
        W1 ──┐
             ├──▶ W2 ─┐
        W3 ──┴──▶ W4 ─┼──▶ W5 (paper writer + reviewer gate)
                       ├──▶ W6 (blog / worklog / wiki)
                       ├──▶ W7 (chat + span redaction)
                       └──▶ W10 (bench egress panel)

        W3 ──▶ W8 (folder watcher + LiteParse + auto-tag)

        W3, W7, W8 ──▶ W9 (Settings UI)
```

## Execution plan

1. **W1, W3 in parallel** (no shared files, independent). Two worktrees.
2. **W2** once W1 lands (sequential — W2 wraps W1's fixed callers).
3. **W4** once W3 lands.
4. **W5, W6, W7, W8, W10 in parallel** once W2 + W4 are in.
   Five worktrees. Each gets a `fullstack-developer` subagent for
   implementation and a `code-reviewer` subagent gate before merge.
5. **W9** last — it depends on W7 and W8 surfaces existing.

Per-worktree merge order back to `main`: W1 → W3 → W2 → W4 →
{W5, W6, W7, W8, W10 (any order)} → W9.

## Validation flow

When all workstreams have landed, the demo we can show ourselves
(and then a non-CS test user) is:

1. Create a new project "Scribe v4".
2. Add `~/Documents/scribe-v4/` to watched folders.
3. Drop in: `results-Q1-2026.xlsx`, `methods-draft.md`,
   `related-work-notes.md`, `intro-outline.md`.
4. Auto-tag heuristic suggests `privacy:local-only` on the results
   file. Confirm.
5. Open the Papers surface → "Generate Introduction".
6. Open the bench TUI → see one `data.egress paper.generate_paper →
   gemini  3 entries assembled, 1 stubbed, 4.1 KB sent`.
7. Click the event → see the redaction map showing
   `results-Q1-2026.xlsx → [private — file — …]`.
8. Open the egress dashboard → see today's totals per surface, per
   project. Filter "Scribe v4" → see "tagged content sent: 0 bytes."

If all eight steps work end-to-end with no leaks and no perf
regression, the prototype is validated.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Cloud model paraphrases the stub instead of preserving it verbatim | Post-hoc verification of stub presence in response; retry once; fall back to local generation if still missing |
| Tag-resolving assembler is on every cloud-call hot path | Perf-budget enforcement (workstream standard #4); assembler is pure-Python string ops, should be fast |
| Auto-tag heuristic false negatives (a sensitive file isn't tagged) | Project-level `privacy_default: strict` is the safety net; default to suggesting tags, never to silently leaking |
| LiteParse Python binding doesn't ship a wheel for our platform | Fall back to PyPDF2 for now; LiteParse becomes optional dependency. Document the gap. |
| Reviewer-surface gate UX is confusing for users | The reviewer surface is already an advanced feature; gate copy is precise ("This surface needs cloud reviewers and a file in this project is marked private. Override?") |
| Re-embedding existing knowledge nodes (L-1 fix) is slow on large workspaces | Run as background migration with progress reporting; allow user to defer |

## Out of scope — explicitly deferred

- Full prompt-response transcript storage (L-3 fix)
- Google Drive / Dropbox ingest
- Feedback button rework
- Wizard rework
- Public release notes / changelog
- Hardware-tier guidance and local-model recommendations
- Reviewer-surface degradation UX polish (basic gate only this week)
- GitHub-as-private-storage exploration
