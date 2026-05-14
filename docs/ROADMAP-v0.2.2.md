# v0.2.2 plan

v0.2.1 shipped the three runtime-active capability kinds
(`ingest_source`, `slash_command`, `action_button`) plus discovery
UX (Settings → Capabilities, ⌘K palette merge, in-context action
buttons). v0.2.2 deepens what users can DO with capabilities rather
than adding new framework primitives.

## Goal

Make the wizard's promise true at the *workflow* level — a researcher
should be able to register, answer the wizard, and within an hour
have Gmail + GitHub activity flowing into their bench without
touching code.

## Scope (in priority order)

### 1. Gmail ingest_source — the first real-world capability

Hardest part isn't the runner itself; it's OAuth. The framework
already has Google OAuth scaffolding for Drive (see
`backend/app/routers/google_oauth.py`). Reuse the token-exchange
flow but add the Gmail scope, then write a `GmailIngest` runner that:

- Authenticates with the stored user token
- Polls the user's inbox with label + query filters from config
- Inserts a `email` knowledge node per new message
- Dedups on `message_id`

Manifest example for a Gmail extension:

```yaml
capabilities:
  - kind: ingest_source
    name: gmail
    config:
      poll_interval_seconds: 600
      label_filter: ["Important", "From: advisor@yourdomain.com"]
      max_age_days: 7
```

Estimated work: 1–2 days. Big risk: Gmail API rate limits + scope
gating on free Google Cloud projects.

### 2. action_button targets beyond knowledge_node

Today only `knowledge_node` is a supported target. v0.2.2 adds:

- `chat_message` — re-use the existing PromoteButton renderer slot;
  add a hook for extension-supplied actions next to it. Enables
  things like "Cite this in paper", "Send to Slack", "Open in
  Linear".
- `draft` — actions on draft cards in the Drafts surface.

The plumbing is small per target: each renderer needs the
`useItemActions(target, item)` hook + a small action button row.
Estimated work: half a day per target.

### 3. surface_widget — the third runtime kind

Today reserved schema-only. v0.2.2 ships the first runtime: a
right-side panel slot in the Advisor surface that extensions can
fill. Useful for "current research question" displays, weekly goal
reminders, etc.

Open question: how invasive is the widget contract? Three options to
investigate:

- **iframe** — most isolated, highest UX friction (loading states,
  styling mismatch).
- **react-server-component fetch + plain JSX** — extension ships a
  JSX module; framework imports and renders it. Same trust model as
  Python runners.
- **declarative cards** — extension declares the data shape +
  template; framework renders. Most constrained, safest.

Lean toward declarative cards for v0.2.2; iframes for v0.3.

### 4. wizard preview shows installed capabilities

When an extension matches in the wizard, the preview pane only shows
the personas + taxonomy. v0.2.2: also surface the extension's
capabilities ("Plus 3 capabilities: scan local files, mark as
decision, archive node") so users see what they're opting into.

Estimated work: 2 hours (frontend-only change in PreviewPane).

### 5. Capability authoring docs polish

- Inline screenshots in CONTRIBUTING.md showing the Settings tab,
  palette entries, action buttons in context.
- A `cookiecutter`-style script: `npm run new-extension <id>` scaffolds
  a manifest + persona stubs + capability template.

Estimated work: half a day.

## Out of scope for v0.2.2

- Multi-tenant capability isolation (Phase 3+).
- Capability sandboxing (iframe / WASM). Still trust-the-PR.
- Per-user capability enable/disable. Today capabilities are
  global-per-deployment.
- Marketplace UI for browsing community extensions. Needs a registry
  service first.

## v0.3 and v0.4 — the LEGO ceiling, broken adaptively

The arch as of v0.2.1 is structured so v0.3 and v0.4 are *additive*,
not refactors. Specifically:

### v0.3 — capability runners as installable Python packages

Today: a new `ingest_source` requires a PR into
`backend/app/capabilities/registry.py`.

After v0.3: `pip install workspaceos-gmail-ingest` and the runner
auto-registers. Authors declare in their `pyproject.toml`:

```toml
[project.entry-points."workspaceos.ingest_sources"]
gmail = "workspaceos_gmail_ingest:GmailIngest"
```

The framework already has `discover_entry_points()` stubs in
`registry.py`, `slash.py`, `actions.py`, and `ai_client.py`. v0.3
flips them from no-op to `importlib.metadata.entry_points(...)` scans.
**Estimated work: 1 day.** No registry rewrite needed.

### v0.4 — surface types as a registry

Today: surfaces are dispatched by a `getSurfaceRenderer()` lookup in
`frontend/lib/bench/surface-registry.ts`. The four in-tree renderers
are registered in `register-surfaces.ts`.

After v0.4: extensions ship their own React component + a manifest
that imports it. A new surface type is one registration call, not a
fork.

The dispatch surface is already table-driven; v0.4 adds the manifest
hook for extension-supplied renderers. **Estimated work: 1 week**
(the registration mechanism is small, the trust-model design is the
hard part).

### v0.4 — composable wizard

Today: 7 fixed questions. Wizard schema reserves
`wizard_fragments: List[Dict]` on `ExtensionManifest` (declared, runtime
ignored) so manifests authored today stay forward-compatible.

After v0.4: extensions declare wizard fragments; user picks which
extension's wizard variant to run.

## Stop conditions

v0.2.2 ships when:

1. Gmail extension exists, OAuth works, ingest runs end-to-end with a
   real Gmail account (not a mock).
2. At least one `chat_message` action_button capability ships in
   `bench-extras` ("Promote to knowledge node" reframed as a
   capability instead of hardcoded).
3. One `surface_widget` runtime ships, with a working example in
   `bench-extras` ("Today's open questions" panel on Advisor).
4. CONTRIBUTING.md has screenshots and the new scaffolder script
   works from a clean checkout.

## Risk register

| Risk | Mitigation |
|---|---|
| Gmail OAuth gating (Google needs app verification for prod) | Ship for dev / single-user use only; document the manual verification path |
| Per-target action_button complexity creep | Stop at chat_message + draft; defer paper + project to v0.2.3 |
| surface_widget design churn | Cap v0.2.2 to declarative cards; document iframe as a possible v0.3 escape hatch |
| Wizard preview noise from capability list | Limit to 3 most relevant; collapse the rest behind "+ N more" |
