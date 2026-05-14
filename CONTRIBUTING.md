# Contributing to WorkspaceOS

The highest-leverage contribution right now is **a new content
extension** for a domain you actually work in. This guide focuses on
that path. Core code contributions are also welcome — see the bottom
of this doc.

## Authoring a content extension

A content extension is a folder under `config/extensions/<your-id>/`.
No Python, no JavaScript, no build step. Just YAML and text files
the wizard's loader picks up at boot.

### 1. Pick an id

Lowercase, kebab-case, matches the folder name. Examples:
`indie-founder`, `phd-student`, `data-platform-engineer`.

The id is permanent — the wizard remembers which extension produced
each user's config, and renaming it later orphans those records.

### 2. Copy an existing extension

Closest to what you want:

```bash
cp -r config/extensions/bio-research config/extensions/your-id
cd config/extensions/your-id
```

You'll get this layout:

```
your-id/
├── manifest.yaml
├── personas/
│   ├── cofounder.yaml      # 3–4 cofounder personas
│   └── research.yaml       # 5–6 research reviewers (optional)
├── taxonomies/extra.yaml   # node types added to base 7
└── prompts/worklog/
    ├── weekly.txt
    ├── monthly.txt
    └── quarterly.txt
```

### 3. Rewrite `manifest.yaml`

```yaml
id: your-id                  # MUST match folder name
name: Your Domain
description: One paragraph — what this extension covers and who it's for.
version: 0.1.0
author: your-github-handle

matches:
  # Substring match against the user's free-text domain answer (+2 each)
  domain_keywords:
    - your domain
    - related synonym
    - specific subfield
  # Wizard audience ids — see frontend/lib/onboarding/types.ts (+1 each)
  audience_any:
    - peer_researchers
    - customers
  # Wizard primary_outputs ids (+1 each)
  outputs_any:
    - papers
    - blog_posts

personas:
  cofounder: ./personas/cofounder.yaml
  research:  ./personas/research.yaml      # omit this line if you don't ship a research pool
taxonomy_extra: ./taxonomies/extra.yaml    # omit if no domain-specific node types
worklog_templates:                          # omit if cadence templates not customized
  weekly:    ./prompts/worklog/weekly.txt
  monthly:   ./prompts/worklog/monthly.txt
  quarterly: ./prompts/worklog/quarterly.txt
```

**Scoring threshold is 2.** Make sure your `domain_keywords` will
catch the user's likely phrasing — singular keyword hit = +2 already
crosses. If your extension is specialized (e.g. "ML compilers"), use
3–4 specific keywords. If broad (e.g. "biology"), 6–10 keywords spans
the synonyms.

### 4. Write the persona pools

Each persona is a real person, archetype, or famous figure relevant
to your domain. The `system_prompt` is what the LLM uses as that
persona's lens during chat — write it in 2nd person addressing the
AI, mention the user's domain specifically, keep it 2–4 sentences.

`personas/cofounder.yaml`:

```yaml
pool_id: cofounder
label: Co-Founder
mode_label: Co-Founder
personas:
  - id: stable_snake_case_id
    name: Famous Person Or Archetype     # max ~24 chars
    color: "#hexcode"                     # distinct from siblings; tailwind-flavored
    system_prompt: |
      You are <name>. You critique <domain> from <specific lens>. You ask
      <the question this persona is known for>. You're skeptical of
      <the failure mode this persona spots>.
```

3–4 cofounder personas. Mix lenses (e.g., one operator, one
investor, one growth, one customer). Each prompt should make the
persona behave noticeably differently from siblings.

`personas/research.yaml`: same shape, 5–6 reviewers. Each one models
a distinct critique lens: technical rigor, novelty/positioning,
writing clarity, practical impact, design elegance, communication.

**Persona name guidance.** Real names are fine and produce stronger
LLM behavior, but only use someone's name if they're a public figure
who's published widely in this field. For private practitioners or
unfamiliar figures, use archetypes ("Operator-Scientist") so we don't
misrepresent anyone.

### 5. Write the taxonomy extras (optional)

The base taxonomy has 7 node types: `decision`, `claim`, `hypothesis`,
`question`, `rejection`, `blocker`, `insight`. Your extension can add
domain-specific node types — things users in your domain track that
the base set doesn't capture.

`taxonomies/extra.yaml`:

```yaml
name: your_id_extra
node_types:
  - id: strain                          # snake_case, stable
    label: Strain                        # human-friendly, max ~18 chars
    color: "#10b981"
    description: An engineered strain — genotype, parent, intended phenotype
```

Keep additions to 2–5 nodes. Too many overwhelms the knowledge graph
palette.

### 6. Write the worklog prompts (optional)

The base worklog prompts are generic. Domain-tuned prompts produce
much better progress reports — they reference domain-specific
artifacts (constructs, ablations, customer interviews) and adopt the
domain's voice.

See `config/extensions/bio-research/prompts/worklog/weekly.txt` and
`ai-research/prompts/worklog/weekly.txt` for two contrasting examples.

Each cadence (`weekly.txt`, `monthly.txt`, `quarterly.txt`) is plain
text with H2-section instructions. The user's specific domain text
is injected by the generator — don't hardcode the domain.

### 7. Test it locally

```bash
docker compose restart backend
```

The loader picks up your extension on next boot. Then:

```bash
# Test that the matcher scores your extension correctly
curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  http://localhost:9000/api/v1/config/generate \
  -d '{"domain":"<a phrase that should match>", ...}' \
  | grep -E "Matched|extension"
```

Or walk through `/onboarding` in the browser — the preview pane shows
an "Extension: <Your Name> v0.1.0" badge with the match score.

### 8. Submit a PR

- One extension per PR.
- Include 1–2 sample wizard answers in the PR description that
  trigger your extension's match.
- Add a one-liner to README's "Shipped extensions" table.

## Authoring capability extensions (Phase 2)

Three capability kinds are runtime-active today: `ingest_source`,
`slash_command`, `action_button`. `surface_widget` is reserved
schema-only. Capability code lives in the framework
(`backend/app/capabilities/`), registered by name in `registry.py` /
`slash.py` / `actions.py`. Manifests reference runners by name —
this is the trust model: code is reviewed in PR, not file-dropped.

### Adding a new `ingest_source` runner

1. Subclass `IngestSource` in `backend/app/capabilities/<name>.py`:

```python
from app.capabilities.base import IngestContext, IngestSource

class GmailIngest(IngestSource):
    label = "gmail"
    default_poll_interval_seconds = 600       # 10 min

    async def run(self, config: dict, ctx: IngestContext) -> int:
        # Pull from your source.
        # For each new item:
        inserted = await ctx.upsert_node(
            node_type="email",                # custom node type
            title=msg["subject"],
            content=msg["snippet"],
            external_id=msg["id"],            # stable dedup handle
            metadata={"from": msg["from"]},
        )
        if inserted:
            ctx.log("info", f"Ingested email: {msg['subject'][:40]}")
        return ingested_count
```

2. Register it in `backend/app/capabilities/registry.py`:

```python
from app.capabilities.gmail import GmailIngest

INGEST_SOURCES: Dict[str, Type[IngestSource]] = {
    "local_files": LocalFilesIngest,
    "gmail": GmailIngest,                     # ← add
}
```

3. Author an extension that uses it:

```yaml
# config/extensions/gmail-sync/manifest.yaml
id: gmail-sync
name: Gmail Sync
version: 0.1.0
capabilities:
  - kind: ingest_source
    name: gmail                               # ← matches registry key
    config:
      poll_interval_seconds: 600
      label_filter: ["Important"]
```

The scheduler picks it up on next boot. `ctx.log()` events appear in
the bench TUI log; `ctx.upsert_node()` inserts are visible in the
Knowledge surface.

### Adding a new `slash_command`

Two flavors:

**`handler_kind: navigate`** — pure routing, no backend code needed.
Just declare it in your manifest:

```yaml
- kind: slash_command
  name: open_papers
  config:
    label: "Open Papers"
    keywords: [papers, p]
    handler_kind: navigate
    handler_target: /bench?surface=papers
```

**`handler_kind: api_call`** — backend handler does the work. Register
an async function in `backend/app/capabilities/slash.py`:

```python
async def _resync_repos(payload, db, user_id):
    # Do the thing.
    return {"ok": True, "toast": "Resynced 3 repos."}

SLASH_RUNNERS: Dict[str, SlashHandler] = {
    "resync_repos": _resync_repos,
}
```

Then in manifest:

```yaml
- kind: slash_command
  name: resync_repos
  config:
    label: "Resync repos"
    keywords: [git, sync, repo]
    handler_kind: api_call
    handler_target: /capabilities/runners/resync_repos/trigger
```

Handler return shape: `{"ok": bool, "toast": "msg shown to user"}`.

### Adding a new `action_button`

Action handlers receive a `target_id` (the item the user clicked on)
in the payload. Register in `backend/app/capabilities/actions.py`:

```python
async def _send_to_slack(payload, db, user_id):
    node_id = uuid.UUID(payload["target_id"])
    node = await _get_user_node(db, user_id, node_id)
    if node is None:
        return {"ok": False, "error": "Node not found"}
    # … POST to Slack …
    return {"ok": True, "toast": f"Sent to #notes."}

ACTION_HANDLERS = {
    "send_to_slack": _send_to_slack,
}
```

Manifest:

```yaml
- kind: action_button
  name: send_to_slack
  config:
    label: "Send to Slack"
    target: knowledge_node               # which item kind to attach to
    handler_kind: api_call
    visible_when:                        # AND-of-ORs, all optional
      node_type: [decision, insight]
```

`visible_when` is an AND across keys; each value is either a single
match or an array of accepted values (OR within key). Empty
`visible_when: {}` = always show.

Targets supported today: `knowledge_node`. More targets
(`chat_message`, `draft`, `paper`) require small per-renderer
plumbing — happy to take PRs.

### Discovery + UX

Anything you ship under `capabilities:` automatically surfaces in:

- **Settings → Capabilities tab** with a `runtime ready` / `declared`
  badge so users know what's wired vs. forward-compatible-only.
- **⌘K palette** (slash_commands).
- **Item context** (action_buttons render on the target item kind,
  gated by `visible_when`).

## Core contributions

Beyond extensions, areas where help is welcome:

- **More content extensions** (the table above is short).
- **Settings → "Personalize" button** to re-run the wizard with
  prefilled answers.
- **Multi-tenant security pass** — see the Event SSE auth note in
  the README; full multi-tenant deployment needs short-lived SSE
  tokens and per-user event filtering.
- **Test coverage** — backend integration tests live in
  `backend/tests/`. Frontend has no tests yet (would welcome a
  reasonable smoke-test setup).

### Code style

- Python 3.9+: `Optional[]`, `List[]`, `Dict[]` from `typing`, not
  `X | None`.
- Minimal diffs. Don't refactor surrounding code unless the task
  asks for it.
- Follow patterns in adjacent files.
- Run relevant tests before opening a PR.

### Security baseline

- HTML-escape user input rendered in HTML responses.
- Validate URLs before fetching (private-IP block in
  `backend/app/services/repo_context.py` is the reference pattern).
- Scope all queries by `user_id` when the user is authenticated by
  JWT.
- Never log API keys, tokens, or other secrets — usage logging
  already redacts.

## Communication

Open an issue before starting a big change. Small extensions / typo
fixes don't need an issue first.

## License

By contributing you agree your work is MIT-licensed (see
[LICENSE](LICENSE)).
