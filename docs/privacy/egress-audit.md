# Egress Audit — Per-Call Data Flow

> Detailed per-call analysis. Service-level rollup lives in
> [`capability-matrix.md`](./capability-matrix.md); specific bugs in
> [`known-leaks.md`](./known-leaks.md).
>
> **Last updated:** 2026-05-28 against v0.2.6 (commit `a1ec0fe`).

## How to read this doc

For every cloud-egress AI call we record five fields:

| Field | Meaning |
|---|---|
| **Trigger** | Which user action causes the egress (so we know if it's idle or interactive) |
| **Egress payload** | Literal text fields sent in the system + user prompt |
| **Identifiability** | LOW / MEDIUM / HIGH / VERY HIGH — see scale below |
| **Inspectable** | Can the user see what was sent? (event stream / usage log / nowhere) |
| **Destination** | Which cloud endpoint receives it |

### Identifiability scale

| Level | Definition | Examples |
|---|---|---|
| **LOW** | No personal content; structural metadata only | A schema ID, a numeric count |
| **MEDIUM** | Topic / search-intent leakage; user could be fingerprinted but not directly identified | Search queries, wizard domain answers |
| **HIGH** | User-authored content + project metadata; correlation across calls trivially identifies the user | Drafts, chat messages, project names |
| **VERY HIGH** | Unpublished IP — research, strategy, code | Paper drafts, methods, agentic chains |

### Inspectability — current global state

- **`event_stream.py`** emits high-level summaries only (e.g. "report
  generated"). The actual prompts and responses are **not** stored.
- **`usage_service.py`** records token counts and estimated cost. The
  literal input/output text is **not** stored (see `ai_client.py:32-43`
  — `log_usage_standalone` is called with the strings but the model
  `AIUsageLog` persists only tokens and cost, not the strings).
- **No prompt/response transcript is currently persisted anywhere.**
  Therefore for every row below, the user has zero audit trail of what
  literal bytes left their machine. The "Inspectable" column reflects
  this — almost universally **NO**.

---

## Egress sites (by surface)

### Foundation: ingest & classification

#### EG-01 — `classifier_service.classify`

| Field | Value |
|---|---|
| **File** | `app/services/classifier_service.py:168` |
| **Trigger** | Any inbox / ingest item arrives without a project assignment |
| **Egress payload** | System prompt + JSON catalogue of **all the user's projects** (id, name, description) + first 4000 chars of the inbound item content |
| **Identifiability** | **HIGH** — every project name in the user's workspace + full item content (which may be an email, calendar entry, draft, etc.) |
| **Inspectable** | NO — only "classified item to project X" surfaces in the event stream |
| **Destination** | Gemini (`gemini-2.0-flash`) |

#### EG-02 — `file_ingest_service.auto_tag`

| Field | Value |
|---|---|
| **File** | `app/services/file_ingest_service.py:90` |
| **Trigger** | User uploads a file via the Files surface |
| **Egress payload** | Filename, MIME type, **first 2000 chars of the file contents** |
| **Identifiability** | **HIGH** — filenames frequently contain personal/project info (e.g. `Q2-2026-strategy.pdf`, `dissertation-draft-final.docx`); content preview is unredacted |
| **Inspectable** | NO |
| **Destination** | Gemini (`gemini-2.0-flash`) |

#### EG-03 — `knowledge_extractor.extract_from_chat_turn`

| Field | Value |
|---|---|
| **File** | `app/services/knowledge_extractor.py:248, 304` |
| **Trigger** | Every AI chat turn (advisor or research) — runs per-turn in the background |
| **Egress payload** | Full user-message content + full AI-message content + recent turn history |
| **Identifiability** | **VERY HIGH** — direct user-authored content, including decisions and hypotheses |
| **Inspectable** | NO |
| **Destination** | Gemini (`gemini-2.0-flash`) |
| **Note** | Embedding now local after L-1 extended fix. |

### Generation: drafts & narratives

#### EG-04 — `worklog_service.generate_report`

| Field | Value |
|---|---|
| **File** | `app/services/worklog_service.py:277` |
| **Trigger** | User clicks "Generate weekly/monthly/quarterly report" |
| **Egress payload** | Commits-by-project map, weekly commit breakdown, papers list, **drafts grouped by status** (titles + status), sync run summary, user-supplied goals, additional instructions |
| **Identifiability** | **HIGH** — project names, commit counts, draft titles, often goals stated in personal terms |
| **Inspectable** | NO — only "report generated" surfaces in the event stream |
| **Destination** | Gemini (`gemini-2.0-flash`) |

#### EG-05 — `memory_service.update_wiki_summary`

| Field | Value |
|---|---|
| **File** | `app/services/memory_service.py:455` |
| **Trigger** | Background sync or manual wiki regenerate |
| **Egress payload** | Project context blocks (joined memory entries) + previous wiki summary |
| **Identifiability** | **HIGH** — every notable memory entry the user has accumulated |
| **Inspectable** | NO |
| **Destination** | Gemini (`gemini-2.0-flash`) |

#### EG-06 — `blog_service` / `ai_generation`

| Field | Value |
|---|---|
| **File** | `app/services/blog_service.py:194`, `ai_generation.py:173/246/311` |
| **Trigger** | User clicks "Generate draft" |
| **Egress payload** | Seed prompt + memory context + style/voice preference summary |
| **Identifiability** | **HIGH** |
| **Inspectable** | NO |
| **Destination** | Whatever `CLOUD_AI_PROVIDER` resolves to (default Gemini) |

#### EG-07 — `agentic_generation.run`

| Field | Value |
|---|---|
| **File** | `app/services/agentic_generation.py:59, 122` |
| **Trigger** | Generation in agentic mode |
| **Egress payload** | Writer step → seed + memory context. Reviewer step → writer's output for critique. |
| **Identifiability** | **HIGH** |
| **Inspectable** | NO |
| **Destination** | Gemini (writer) + **OpenAI (reviewer, hard-coded — see [L-2](./known-leaks.md#l-2))** |

#### EG-08 — `methods_drafter` / `diagram_service` / `venue_service`

| Field | Value |
|---|---|
| **Files** | `app/capabilities/methods_drafter.py:163`, `diagram_service.py:204/286/447`, `venue_service.py:203` |
| **Trigger** | Specific surface actions (paper methods, diagram, venue suggest) |
| **Egress payload** | Surface-specific context (paper section, content to diagram, project profile for venue) |
| **Identifiability** | **HIGH** |
| **Inspectable** | NO |
| **Destination** | Gemini |

### Chat & advisors

#### EG-09 — Cofounder roundtable (`chat_service.send_to_advisors`)

| Field | Value |
|---|---|
| **File** | `app/services/chat_service.py:463` and `advisors.py:152` (router pre-call) |
| **Trigger** | User sends a message in the R surface |
| **Egress payload** | (a) Router call: just the user message text. (b) Per-advisor call: advisor persona prompt + **full conversation history (last 20 turns)** + workspace/memory/repo context blocks + user message |
| **Identifiability** | **HIGH** — entire conversation, including unstated context the user typed into earlier turns |
| **Inspectable** | NO |
| **Destination** | Gemini, fan-out 3–4× per message |
| **Note** | Workspace / memory / repo context are user-controlled toggles — when enabled, project content is included in every advisor call |

#### EG-10 — Research roundtable (`research_service.send_message`)

| Field | Value |
|---|---|
| **File** | `app/services/research_service.py:420` |
| **Trigger** | User sends a message in the A surface |
| **Egress payload** | Reviewer persona prompt + Semantic-Scholar-grounded literature context + last 20 conversation turns + user message |
| **Identifiability** | **VERY HIGH** — unpublished research direction |
| **Inspectable** | NO |
| **Destination** | Gemini, fan-out 5–6× per message |

### Papers

#### EG-11 — `paper_service.generate_paper` and `regenerate_version`

| Field | Value |
|---|---|
| **File** | `app/services/paper_service.py:464, 876, 1120` |
| **Trigger** | User starts a paper generation or revision |
| **Egress payload** | Full paper draft (multiple sections), target venue, additional instructions, prior version content for revision |
| **Identifiability** | **VERY HIGH** — unpublished academic IP |
| **Inspectable** | NO |
| **Destination** | Gemini (writer) + GPT-4o (some passes) |

#### EG-12 — `paper_reviewers.run_roundtable`

| Field | Value |
|---|---|
| **File** | `app/services/paper_reviewers.py:198, 424` |
| **Trigger** | Paper pipeline reviewer pass |
| **Egress payload** | **Entire paper text + venue context**, sent in parallel to multiple reviewer personas |
| **Identifiability** | **VERY HIGH** |
| **Inspectable** | NO |
| **Destination** | **Mix of Gemini, OpenAI, and Anthropic** (deliberate provider diversity for genuine critique) |

### Onboarding

#### EG-13 — `config_generator._generate_with_llm`

| Field | Value |
|---|---|
| **File** | `app/services/config_generator.py:275` |
| **Trigger** | User completes the 7-question wizard with no matching extension |
| **Egress payload** | All 7 free-text wizard answers — domain, primary outputs, audience, dream advisor panel, tracked artifacts, cadence, stage |
| **Identifiability** | **MEDIUM** — domain + audience + advisor preferences can fingerprint, but no direct PII |
| **Inspectable** | Partial — the wizard SSE stream surfaces a "generating" event with stage labels, but not the literal answers |
| **Destination** | Gemini (`gemini-2.0-flash`) |

### Knowledge / search

#### EG-14 — `knowledge_service.query_embedding` **(BUG — should be local)**

| Field | Value |
|---|---|
| **File** | `app/services/knowledge_service.py:30` |
| **Trigger** | Every knowledge-graph search query |
| **Egress payload** | The raw search query text |
| **Identifiability** | **MEDIUM** — reveals what the user is looking for |
| **Inspectable** | NO |
| **Destination** | Whatever `CLOUD_AI_PROVIDER` resolves to — embeddings should be local-only |
| **See** | [L-1](./known-leaks.md#l-1) |

### Non-LLM but data-egress sensitive

#### EG-15 — `routers/feedback.py` (GitHub issue creation)

| Field | Value |
|---|---|
| **File** | `app/routers/feedback.py:99-112` |
| **Trigger** | User clicks the feedback button and submits |
| **Egress payload** | User-typed title + body + auto-context block (`surface`, `project_id`, `url`, `viewport`, `user_agent`, last 10 bench events) + submitter user ID |
| **Identifiability** | **HIGH** — `url` and `project_id` are direct internal identifiers; recent bench events reveal what the user was doing |
| **Inspectable** | YES — the "auto-context that will be attached" disclosure is shown in the modal before submit (`FeedbackButton.tsx:213`). This is the only egress site with pre-submit transparency. |
| **Destination** | `api.github.com` — creates a **public** issue on `Chesterguan/WorkspaceOS` by default |
| **Note** | Sets the upper bound on what an honest disclosure UI should do for every other egress in this doc |

#### EG-16 — `publish_service` (LinkedIn / Dev.to / Hashnode / GitHub Releases)

| Field | Value |
|---|---|
| **File** | `app/services/publish_service.py` |
| **Trigger** | User explicitly clicks "Publish" |
| **Egress payload** | The draft body — already explicitly opted into for publication |
| **Identifiability** | **VERY HIGH** by definition; user is publishing |
| **Inspectable** | YES — user sees and approves the content before clicking publish |
| **Destination** | External platforms |
| **Note** | Explicit user action — not a privacy concern, listed for completeness |

---

## Cross-cutting observations

1. **Background egress is the real risk.** EG-03 (knowledge extractor)
   and EG-05 (wiki summary) run **automatically** on every chat turn /
   background sync. The user never sees a "this will send X to Y"
   prompt. Foreground egress (paper generation, blog draft) is at
   least user-initiated.

2. **No prompt/response transcript exists today.** The user has no way
   to audit what was sent for any feature except EG-15 (feedback
   modal). To honestly claim a privacy posture we must either:
   - persist a redacted transcript log (storage + UI cost), or
   - move enough work local that the cloud-going traffic is small
     enough to surface in the modal-style pre-confirm pattern.

3. **Hard-coded `OpenAIClient()` constructions are leak vectors.**
   See [L-2](./known-leaks.md#l-2). Even if the user sets
   `CLOUD_AI_PROVIDER=ollama`, EG-07, EG-11, and EG-12 still call
   OpenAI directly.

4. **Identifiability is highest exactly where users care most.** Paper
   drafts (EG-11/12) and research conversations (EG-10) carry the
   highest stakes — and they're the surfaces that genuinely need
   cloud quality. Any honest privacy story has to address this
   tension head-on (not pretend it doesn't exist).
