# Privacy Investigation — WorkspaceOS v0.2.6

> **Status:** investigation. No code changes yet. This folder is the
> evidence base for the upcoming privacy / capability-matrix design.
>
> **Last updated:** 2026-05-28
> **Maintainer:** @chesterguan

## Why this exists

v0.2.6 user testing surfaced three blockers for non-CS users:

1. **GitHub-centric flows** — feedback button, publishing, and
   onboarding assume users know what GitHub is.
2. **No local-file / cloud-drive ingest** — users expect the bench to
   read their existing files, not the other way around.
3. **Privacy** — data is sent to LLM APIs (Gemini, OpenAI, Anthropic)
   on most generation paths. Researchers with unpublished data and
   founders with confidential strategy cannot tolerate this.

Before designing a fix, we need a **measurable, provable** account of
exactly what data leaves the user's machine today, which calls actually
require cloud quality, and which can run on a local model. This folder
is that account. Hardware / model recommendations come after — once
we have measured baselines from real local-model runs.

## Methodology

1. **Static audit.** Every `get_cloud_client()` and `OpenAIClient()`
   call site in `backend/app/services/` and `backend/app/capabilities/`
   was located via grep. For each, the surrounding prompt construction
   was read to determine the payload composition.
2. **Surface mapping.** Each call was mapped back to one of the six
   bench surfaces (R/A/D/P/K/W) or to a foundation service (ingest,
   memory, classifier, wizard).
3. **Identifiability classification.** For each call we record the
   literal payload fields and rate identifiability on a four-level
   scale (LOW / MEDIUM / HIGH / VERY HIGH).
4. **Inspectability check.** For each call we record whether the user
   can see what was sent — via the bench TUI event stream
   (`event_stream.py`) and/or the usage log (`usage_service.py`).

## What's in this folder

| File | Purpose |
|---|---|
| [`capability-matrix.md`](./capability-matrix.md) | Service-level summary — cloud / local / leak-status / redactable |
| [`egress-audit.md`](./egress-audit.md) | Per-call detail — payload fields, identifiability, inspectability, measured-bytes (placeholder) |
| [`known-leaks.md`](./known-leaks.md) | Specific bugs where the privacy contract is violated today |
| [`measurement-and-redaction.md`](./measurement-and-redaction.md) | How to *measure* per-call egress + how to *redact* sensitive spans with local-only placeholders before egress |
| `local-model-recommendations.md` | **Deferred.** Will be written after baselines are measured. |
| `hardware-recommendations.md` | **Deferred.** Will be written after baselines are measured. |

## What's NOT here yet (deliberate)

- **Hardware recommendations.** Premature. We need measured outputs
  from each local-model candidate (latency, quality, JSON-mode
  reliability) before committing public-facing minimum specs.
- **Local model picks per task.** Same reason. Today's table lists
  *candidates*; the recommendations doc will name one model per task
  with evidence.
- **The fix.** This folder is the investigation. The design and
  implementation plan land separately under
  `docs/superpowers/specs/` and `docs/superpowers/plans/`.

## How to use this folder

- If you want the **30-second view**: read `capability-matrix.md`.
- If you want to know **what specifically goes to which cloud** for a
  given feature: read `egress-audit.md`.
- If you want to know **what's broken right now**: read
  `known-leaks.md`.
- If you want to understand **how we'd quantify the leak and redact
  sensitive spans before egress**: read `measurement-and-redaction.md`.
