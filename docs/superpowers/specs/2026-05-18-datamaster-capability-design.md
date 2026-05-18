# DataMaster Capability Extension — Design

**Date:** 2026-05-18
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** chesterguan + Claude

## Summary

Embed [DataMaster](https://github.com/sjtu-sai-agents/DataMaster) (built on
[EvoMaster](https://github.com/sjtu-sai-agents/EvoMaster)) into WorkspaceOS
**not as a framework merge** but as an opt-in Phase-2 capability that an AI
researcher can trigger from the bench. WorkspaceOS stays the workbench; the
heavy autonomous data-engineering agent runs as an isolated sidecar service.
One slash command — `/run_data_experiment` — assembles a task brief from the
project's knowledge graph, runs DataMaster's DataTree search in the sidecar,
streams the trajectory into the TUI event log, and lands the result as an
`Experiment` node linked to the Claims/Experiments that seeded it.

This proves the Phase-2 capability pattern further (after `methods-drafter`,
`preprints`, `github-tools` in v0.2.6) and is the model for community
contributors to wrap other heavy agents on the same rails.

## Goals

- AI researchers can run a DataMaster data-pipeline search from inside the
  bench, grounded in their project context.
- Zero framework coupling: WorkspaceOS never embeds EvoMaster's
  orchestrator, sandbox, or memory.
- The sidecar job API is a clean, documented contract any contributor can
  implement for a different heavy agent (EvoMaster-generic later).
- Results feed the knowledge graph so the bench learns from each run.

## Non-goals (YAGNI, v1)

- EvoMaster generic agent runner (ML-Master / X-Master / etc.).
- EvoMaster run-level self-evolution loop.
- Auto-handoff to `/draft_methods`.
- GPU scheduling, job queueing, multi-job concurrency per user.
- Any UI beyond the trigger form + existing TUI / Knowledge surfaces.
- Live DataMaster in CI.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Where does the agent execute? | External sidecar service (own container, own keys, own GPU). |
| v1 scope | DataMaster only, one `slash_command` capability `run_data_experiment`. |
| Task input | KG-grounded brief assembled from the project + one free-form objective line + dataset pointer. |
| Result mapping | `Experiment` node (objective, score, pipeline summary, artifact links) auto-linked to seeding Claims/Experiments; full trajectory streamed to TUI and retained. |
| Sidecar comms | SSE streaming relay (Approach A); `GET /jobs/{id}` poll is the documented fallback + restart-recovery path. |

## Architecture

Five well-bounded units with explicit interfaces:

| Unit | Responsibility | Interface | Depends on |
|---|---|---|---|
| `config/extensions/datamaster/manifest.yaml` | Declare the slash command + sidecar URL/knobs (pure data, no code) | YAML capability block | extension loader |
| Sidecar job API | Run DataMaster, emit trajectory + result | HTTP contract (below) | DataMaster/EvoMaster, own `.env` keys |
| `backend/app/capabilities/datamaster_runner.py` | Assemble brief, own job, relay SSE, ingest result | `POST /capabilities/runners/run_data_experiment/trigger` | KG read, job table, bench event stream, sidecar client |
| `data_experiment_jobs` table | Job state, ownership, restart recovery | Alembic migration | — |
| Trigger form (frontend) | Collect objective + dataset + max-minutes | Reuses ⌘K capability-trigger path | existing TUI / Knowledge surfaces |

### Extension manifest

`config/extensions/datamaster/manifest.yaml`, mirroring the `methods-drafter`
shape:

```yaml
id: datamaster
name: DataMaster Data Experiment
description: |
  Runs SJTU DataMaster's data-centric DataTree search as an isolated
  sidecar. Grounds the task in the project's knowledge graph; lands the
  result as an Experiment node with the final score and pipeline summary.
version: 0.1.0
author: workspaceos

matches:
  domain_keywords: []   # opt-in only — user enables via Settings

capabilities:
  - kind: slash_command
    name: run_data_experiment
    description: |
      Run a DataMaster data-pipeline search for the current project,
      grounded in the knowledge graph.
    config:
      label: "Run DataMaster experiment"
      keywords: [datamaster, data experiment, pipeline search, run datamaster]
      icon: "flask-conical"
      handler_kind: api_call
      handler_target: "/capabilities/runners/run_data_experiment/trigger"
      sidecar_base_url: "http://datamaster:8800"  # user-configurable in Settings
      sidecar_token: ""        # optional shared bearer; Fernet overlay if set
      default_max_minutes: 30
      allowed_dataset_root: "" # path-kind datasets must live under this root
```

### Sidecar job API (the contributor extension point)

Any agent backend that implements this contract works with the same
WorkspaceOS runner. v1 ships a DataMaster implementation.

- `POST /jobs`
  `{ job_id, objective, brief_md, dataset:{kind:"hf"|"path", ref}, limits:{max_minutes} }`
  → `{ status:"accepted" }`
- `GET /jobs/{job_id}/stream` → SSE events:
  - `phase` — high-level stage
  - `node` — DataTree node (`red`=explore / `black`=exploit) with summary
  - `metric` — validation metric update
  - `log` — free-form line
  - `done` — `{ score, pipeline_summary_md, artifacts:[{name, uri}] }`
  - `error` — `{ message }` (surfaced verbatim in TUI)
- `GET /jobs/{job_id}` → poll fallback + restart recovery:
  `{ status, progress, result? }`
- `POST /jobs/{job_id}/cancel`
- `GET /healthz`

The sidecar is an opt-in compose service on the `workspaceos` network, **not**
in the backend image and **not** started by default
(`docker compose --profile sidecars up datamaster`, or a separate compose
file). It owns its own LLM / Serper / HuggingFace credentials in its own
`.env`.

### Data flow

1. User triggers `/run_data_experiment` from ⌘K → small form: objective
   (textarea), dataset pointer (`hf:<id>` or path), optional max-minutes.
2. `POST /capabilities/runners/run_data_experiment/trigger`
   `{ project_id, objective, dataset, max_minutes? }`.
3. Runner assembles `brief_md` from the **current project's** knowledge
   graph — open `Experiment` nodes, `Claim` nodes, `paper_reference` nodes —
   **all reads scoped by `user_id`**. Empty KG → brief notes "no prior
   context", run still proceeds.
4. Create a `data_experiment_jobs` row (`queued`).
5. `POST {sidecar_base_url}/jobs` (with optional bearer token).
6. Open SSE to `{sidecar_base_url}/jobs/{id}/stream`; relay each event into
   the **existing bench event stream** (same SSE infra as wizard generation /
   capability runs). Persist phase/metric checkpoints on the job row.
7. On `done`: create an `Experiment` knowledge node (title = objective; body
   = pipeline summary + final score + artifact links), `user_id`-scoped;
   auto-link to the seeding `Claim`/`Experiment` nodes via the **v0.2.6 F3
   linking helper**. Set `result_node_id`, status `done`, emit completion
   event.
8. On `error` / timeout / cancel: status `error`, surface the sidecar error
   body verbatim in the TUI (v0.2.6 "Gemini error body surfaced" pattern); no
   node created.

### Data model

One new table, one Alembic migration. The `Experiment` node uses the
existing knowledge-node table — no change there.

`data_experiment_jobs`:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `user_id` | fk → users | scoping |
| `project_id` | fk → projects | |
| `sidecar_job_id` | text | id sent to sidecar |
| `objective` | text | |
| `dataset_ref` | text | `hf:<id>` or validated path |
| `status` | enum | `queued\|running\|done\|error\|cancelled` |
| `score` | float null | from `done` |
| `result_node_id` | fk → knowledge nodes, null | the Experiment node |
| `error` | text null | verbatim sidecar error |
| `created_at` / `updated_at` | timestamptz | |

### Frontend

Minimal, reusing existing patterns (no new shared modules — CLAUDE.md rule):

- `/run_data_experiment` appears in the ⌘K palette automatically (slash_command
  capability → palette, same as `draft_methods`).
- Trigger opens a small dialog: objective textarea + dataset pointer field +
  optional max-minutes. (Richer than methods-drafter's payload, so a small
  form rather than a one-shot api_call; reuse the existing capability-trigger
  dialog scaffolding.)
- Trajectory renders in the existing TUI event log — no new panel.
- Result `Experiment` node appears on the Knowledge surface like any other
  node, with its links.

## Error handling

| Case | Behavior |
|---|---|
| Sidecar unreachable at trigger | Clear "DataMaster sidecar not configured / reachable at `<url>`" in TUI; job row marked `error` immediately; nothing dangling. |
| Run exceeds `max_minutes` | Backend `POST /jobs/{id}/cancel`, job `error`. |
| Sidecar emits `error` | Error body surfaced verbatim in TUI; no node. |
| Backend restart mid-run | On startup, `running` jobs reconciled via `GET /jobs/{id}` (poll path doubles as recovery). |
| Empty project KG | Run proceeds with objective only; brief notes "no prior context". |
| Concurrent run, same user | Rejected with a clear message (no queue in v1). |
| Invalid dataset pointer | Reject before job creation (see Security). |

## Security

- Sidecar holds its **own** LLM / Serper / HF keys in its **own `.env`**.
  WorkspaceOS never proxies or logs them (isolation; "never log secrets").
- Optional shared bearer token between backend ↔ sidecar, stored in the
  capability config (Fernet runtime overlay if the user sets it).
- All knowledge-graph reads and node writes scoped by `user_id`.
- Dataset pointer validated: allow `hf:<id>` or a path **under
  `allowed_dataset_root`**; reject arbitrary URLs / paths outside the root
  ("validate before fetching").

## Testing

- **Fake sidecar** (FastAPI test double implementing the job API) — drives
  happy-path, sidecar-error, timeout, poll-fallback, restart-recovery.
- Unit: brief assembly from a seeded KG → expected markdown (incl. empty-KG
  case).
- Unit: SSE event → bench-event mapping; `done` → Experiment node + links;
  `error` → no node, job `error`.
- Migration up/down for `data_experiment_jobs`.
- Dataset-pointer validation: accept `hf:<id>` and in-root path; reject
  out-of-root path and URLs.
- No live DataMaster in CI — the fake sidecar is the boundary, consistent
  with existing capability tests.

## Open follow-ups (post-v1)

- Generic EvoMaster runner reusing the same job contract.
- Optional `/draft_methods` handoff from a finished Experiment node.
- A reference sidecar Dockerfile + compose profile shipped under
  `sidecars/datamaster/` so contributors have a working starting point.
