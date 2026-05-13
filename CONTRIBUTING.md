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

## Reserving capability extensions for Phase 2

If you're writing an extension that you want to eventually wire to an
ingest source / slash command / surface widget, you can declare
capabilities in `manifest.yaml` now even though the runtime ignores
them in Phase 1. This keeps the manifest forward-compatible:

```yaml
capabilities:
  - kind: ingest_source
    name: gmail
    description: Pull emails into the worklog activity feed
    config:
      poll_interval_minutes: 30
      label_filter: ["Important"]
```

Capability kinds reserved: `ingest_source`, `slash_command`,
`action_button`, `surface_widget`. See
`backend/app/schemas/extension.py` for the canonical type.

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
