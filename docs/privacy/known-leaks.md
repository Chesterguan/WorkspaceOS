# Known Privacy Leaks (v0.2.6)

> Specific bugs where the codebase's privacy contract is currently
> violated. These must be fixed before any user-facing "Strict mode"
> can be honestly advertised.
>
> **Last updated:** 2026-05-28 against commit `a1ec0fe`.

## L-1 — Knowledge query embeddings go to cloud

**File:** `backend/app/services/knowledge_service.py:30`

```python
async def query_embedding(query: str) -> List[float]:
    return await get_cloud_client().embed(query)
```

**Why this is a bug.** Embeddings are a foundation operation. Every
other embedding call in the codebase uses `get_local_client()`
(`memory_service`, `consolidation_service`, `extraction_service`,
`knowledge_extractor._embed`). This single line is the odd one out
and sends the user's search query to whatever `CLOUD_AI_PROVIDER`
resolves to.

**Impact.** Every knowledge-graph search reveals the query string to
Gemini (default) or OpenAI. Identifiability: **MEDIUM** (queries reveal
research intent / topic focus).

Adjacent leak in `knowledge_extractor.py:248` (the `_embed` helper) was
also fixed in the same change set.

**Fix sketch.** One-line change: `get_cloud_client()` →
`get_local_client()`. The embedding column is 768-dim — both
`nomic-embed-text` (local default) and the Gemini Matryoshka path
produce 768-dim vectors, so no migration is needed for new entries.
*However:* existing knowledge-node embeddings were generated against
whichever cloud model was active when they were created; mixing local
and cloud embedding spaces in the same column corrupts cosine
similarity. Re-embedding the existing nodes is part of the fix.

---

## L-2 — Hard-coded `OpenAIClient()` constructions bypass the provider router

**Files:**
- `backend/app/services/agentic_generation.py:29` — `OpenAIClient` imported and used directly
- `backend/app/services/paper_reviewers.py:23` — same
- `backend/app/services/paper_service.py:35` — same
- `backend/app/services/agents.py:21` — same

**Why this is a bug.** The whole point of `_build_client(provider)` in
`ai_client.py` is to make provider selection a single config knob
(`CLOUD_AI_PROVIDER`). These four files import `OpenAIClient` directly
and instantiate it via `OpenAIClient()` regardless of the configured
cloud provider.

**Example (`paper_reviewers.py:200-203`):**

```python
cloud = get_cloud_client()
if settings.openai_api_key:
    openai_client: Any = OpenAIClient()
else:
    openai_client = cloud
```

The intent (multi-provider review diversity for genuine critique) is
legitimate for the paper roundtable specifically. But:

1. It silently sends data to OpenAI whenever `OPENAI_API_KEY` is set,
   even if the user has configured Ollama as their cloud provider.
2. It does so for `agentic_generation` and `agents` too, where the
   diversity rationale doesn't apply — those calls aren't designed
   to need OpenAI specifically.

**Impact per file:**

| File | Why it instantiates OpenAI | Diversity-intent legit? | Honest fix |
|---|---|---|---|
| `paper_reviewers.py` | Some reviewers tagged `_OPENAI_REVIEWER_IDS` | YES — by design | Make it explicit: gate behind a `paper_reviewer_providers` setting; in Strict mode skip the OpenAI reviewers and document the degradation |
| `paper_service.py` | Reviewer step uses OpenAI when available | Partial | Same — route through the explicit-settings path |
| `agentic_generation.py` | Reviewer step | NO — undocumented | Should call `get_cloud_client()` like everything else |
| `agents.py` | Mixed | NO | Should call `get_cloud_client()` like everything else |

**Fix sketch.** Add a typed `paper_reviewer_providers: List[str]`
setting that explicitly enumerates which providers the paper-reviewer
roundtable is allowed to call. Remove direct `OpenAIClient()` calls
from `agentic_generation.py` and `agents.py`. Update the event stream
to emit a "cloud call: <provider> for <reason>" event so it becomes
visible.

---

## L-3 — No prompt / response transcript is persisted anywhere

**Files:**
- `backend/app/services/usage_service.py` — persists tokens + cost only
- `backend/app/services/event_stream.py` — emits 200-char summaries
- (no third location)

**Why this is a problem.** Every other row in [`egress-audit.md`](./egress-audit.md)
has "Inspectable: NO" because the literal payload sent to the cloud
isn't stored. The user has no way to verify what data left the
machine, only an aggregate "$0.04 spent today" view.

**This isn't a bug in the strict sense** — it's a deliberate
storage-cost decision. But it's a structural blocker for any
"trust through transparency" privacy posture. You can't show users
what was sent if you didn't keep it.

**Fix sketch.** Add an opt-in `record_prompt_transcript` setting that,
when enabled, persists `{ts, provider, model, system_prompt,
user_prompt, response, project_id}` to a new table with a configurable
retention window (default 7 days). UI: a per-feature toggle in
Settings and a "What was sent?" link on every AI-generated output.
Off by default to keep storage costs predictable; recommended on for
users who care about audit.

---

## L-4 — Feedback button files publicly without warning

**File:** `backend/app/routers/feedback.py:101-112`,
`frontend/components/feedback/FeedbackButton.tsx:236`

**Why this is a bug-shaped UX problem.** The modal footer reads "Files
publicly to `Chesterguan/WorkspaceOS`" — small grey text, easy to
miss. The auto-context block includes `project_id`, `url`, and the
last 10 bench events. A user could plausibly file an issue mentioning
unpublished work and not realise the issue is **world-readable on
GitHub**. The submit button is not gated by an explicit "I understand
this will be public" checkbox.

**Also broken:** when `GITHUB_TOKEN` is unset, the backend returns 503
with no UI affordance — the button is still visible.

**Impact.** Identifiability: **HIGH**. The destination (public) is
worse than the cloud-LLM destinations elsewhere in this doc, because
LLM API logs are at least retained privately by the provider.

**Fix sketch.** Per discussion 2026-05-28, the feedback function is
**out of scope** for the current week. To be revisited with a clearer
non-CS onboarding for GitHub (or a non-GitHub channel) before next
public release. In the meantime:

1. Gate the button on a backend `/feedback/status` endpoint that
   returns `{enabled, channel}`. Hide the button when `enabled=false`.
2. Make the "files publicly" warning prominent — not 10px grey text.
3. Require an explicit checkbox: "I understand this will be visible
   on GitHub."
