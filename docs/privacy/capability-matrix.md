# Capability Matrix — Cloud vs Local

> Service-level summary. Detailed payload audit lives in
> [`egress-audit.md`](./egress-audit.md); specific bugs in
> [`known-leaks.md`](./known-leaks.md).
>
> **Last updated:** 2026-05-28 against `backend/app/services/` as of
> commit `a1ec0fe` (v0.2.6).

## Legend

| Tier | Meaning |
|---|---|
| 🟢 **Local-only** | Already runs locally today, or trivially can. No quality loss. |
| 🟡 **Local-acceptable** | Local can do the work; cloud is meaningfully better for polish. User-toggleable. |
| 🔴 **Cloud-required** | Design or quality intent breaks if forced local. Disable or degrade in Strict mode. |

## Matrix

**Redactable?** column refers to whether the call can be made privacy-safe
with **tag-based redaction** (replace whole tagged files/entries with
stubs at prompt-assembly) and/or **span-based redaction** (regex +
glossary + NER detection of sensitive spans in free-form text). See
[`measurement-and-redaction.md`](./measurement-and-redaction.md).

- **✅ yes (tag)** — surface assembles project content; tagging a file
  as `privacy:local-only` means its content never reaches cloud
- **✅ yes (span)** — surface processes user-typed free-form text;
  glossary + NER detection
- **⚠️ partial** — coverage works for some inputs but not others;
  see notes
- **❌ no** — the call's whole purpose is to operate on the content
  (reviewer judgement, classifier routing); redacting defeats it

| # | Surface / Service | What it does | Tier | Cloud model used today | Redactable? |
|---|---|---|---|---|---|
| **Foundation: memory & embeddings** ||||||
| 1 | `memory_service.add_entry` | 768-dim embedding of every memory entry | 🟢 | — (already local: `nomic-embed-text`) | n/a — local |
| 2 | `memory_service._generate_context_description` | 1–2 sentence descriptor before embedding | 🟢 | — (already local) | n/a — local |
| 3 | `knowledge_service.query_embedding` | Embed search query | 🟢 | **🐛 cloud today — see [leaks](./known-leaks.md#l-1)** | n/a — should be local |
| 4 | `consolidation_service` | Compress old memory entries | 🟢 | — (already local) | n/a — local |
| 5 | `memory_service.update_wiki_summary` | Auto-wiki page per project | 🟡 | `gemini-2.0-flash` | ⚠️ partial — fact-summary needs facts |
| **Foundation: ingest & classification** ||||||
| 6 | `file_ingest_service._extract_text` | PDF/DOCX → text | 🟢 | — (PyPDF2 today; LiteParse swap proposed) | n/a — local |
| 7 | `file_ingest_service.auto_tag` | 3–5 tags + 1 summary sentence | 🟢 | `gemini-2.0-flash` | ❌ useless — content *is* the input |
| 8 | `classifier_service.classify` | Route inbox item → project | 🟢 | `gemini-2.0-flash` | ❌ useless — content *is* the input |
| 9 | `workspace_scanner` | Summarise scanned repo / notes | 🟢 | — (already local) | n/a — local |
| 10 | `repo_context` | Local repo descriptor | 🟢 | — (already local) | n/a — local |
| 11 | `github_sync` label | Tag synced items | 🟢 | — (already local) | n/a — local |
| 12 | `local_ingest_service` | Host-bridge → memory | 🟢 | — (already local) | n/a — local |
| 13 | `knowledge_extractor` | Decisions / claims / hypotheses (structured JSON) | 🟢 | `gemini-2.0-flash` | ❌ useless — content *is* the input |
| 14 | `extraction_service` | Themes from chat | 🟢 | — (already local) | n/a — local |
| **Generation: drafts & narratives** ||||||
| 15 | `worklog_service` | Weekly / monthly / quarterly reports | 🟢 | `gemini-2.0-flash` | ✅ yes (tag) — drafts/papers from tagged projects become stubs |
| 16 | `venue_service` | Suggest publishing target | 🟢 | `gemini-2.0-flash` | ⚠️ partial — project profile partly tagged |
| 17 | `methods_drafter` | Draft methods section | 🟡 | `gemini-2.0-flash` | ✅ yes (tag) — methods file tag drives stub |
| 18 | `blog_service`, `ai_generation` | Blog / social drafts | 🟡 | `gemini-2.0-flash` | ✅ yes (tag) — source-memory tags filter context |
| 19 | `agentic_generation` | Multi-step writer + reviewer | 🟡 | Gemini writer + **OpenAI reviewer (hard-coded — see [leaks](./known-leaks.md#l-2))** | ✅ writer (tag) / ⚠️ reviewer |
| 20 | `diagram_service` (final) | Mermaid / SVG output | 🟡 | `gemini-2.0-flash` | ⚠️ partial — labels via span, structure not |
| 21 | `diagram_service` (intermediate) | Layout / planning steps | 🟢 | — (already local) | n/a — local |
| **Chat & advisors** ||||||
| 22 | `advisors.py`, `chat_service` (R) | Cofounder roundtable | 🟡 | `gemini-2.0-flash` | ✅ yes (span + tag) — span for live text, tag for memory context |
| 23 | `agents.py` | Agent runtime steps | 🟡 | Mixed cloud + local | ⚠️ partial — depends on step |
| 24 | `research_service` (A) | Academic critique pool | 🔴 | `gemini-2.0-flash` | ❌ no — reviewers must judge claims |
| **Papers (cloud-required by design)** ||||||
| 25 | `paper_reviewers.py` | 6-reviewer roundtable | 🔴 | **Gemini + OpenAI + Anthropic mix** | ❌ no — reviewers must judge claims (tag policy: privacy:local-only entries skip the call) |
| 26 | `paper_service.py` | Long-form academic writer / reviser | 🔴 | `gemini-2.0-flash` + GPT-4o | ✅ **yes (tag) — primary use case** |
| **Onboarding** ||||||
| 27 | `config_generator.py` | Wizard domain-config synthesis | 🟡 | `gemini-2.0-flash` | ⚠️ partial — span-based on free-form wizard answers |
| **Non-LLM but data-egress sensitive** ||||||
| 28 | `routers/feedback.py` | POST to `api.github.com` (creates issue) | n/a | github.com (public repo by default) | ✅ yes (tag) — project_id/url stubbed |
| 29 | `publish_service.py` | LinkedIn / Dev.to / Hashnode / GH Releases | n/a | external platforms | n/a — explicit publish action |
| 30 | `usage_service.py` | Persist token counts | 🟢 | local DB only | n/a — local |

## Roll-ups

**By tier:**

- 🟢 Local-only or trivially local: **18 of 30** call sites (60%)
- 🟡 Local-acceptable, cloud-preferred: **9 of 30** (30%)
- 🔴 Cloud-required by design: **3 of 30** (10%) — all in the Papers
  and Research surfaces

**By surface (cloud-required count):**

| Surface | Cloud-required? | Notes |
|---|---|---|
| Roundtable (R) | No — local-acceptable | Quality loss tolerable for personal advice |
| Research (A) | Yes | Critique diversity needs multi-provider |
| Drafts (D) | No — local-acceptable | Long-form quality benefits from cloud |
| Papers (P) | **Yes** | Multi-provider reviewer roundtable is structural |
| Knowledge (K) | No | All extractions are 🟢 in privacy mode |
| Worklog (W) | No — local-acceptable | Personal reports, local 14b sufficient |

## So what

- **The bulk of egress today is unnecessary.** Rows 7, 8, 13, 15, 16
  account for the steady-state classification + extraction +
  summarisation traffic. None of them require cloud quality.
- **Two surfaces are genuinely cloud-bound** (Papers, Research). The
  rest can be local-default with cloud as opt-in polish.
- **Known leaks** (`knowledge_service` query embed; direct
  `OpenAIClient()` in agentic/paper/research code) must be fixed
  before any "Strict" privacy mode can be honestly advertised.
