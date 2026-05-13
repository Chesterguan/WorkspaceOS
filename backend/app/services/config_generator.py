"""Generates a domain config from onboarding wizard answers.

Phase 1 (this file): deterministic stub. Returns a baseline config with
the wizard's domain text spliced into a handful of slots — enough to
exercise the full wizard → preview → apply → reload loop without burning
LLM tokens during UI development.

Phase 2 (next checkpoint): the stub is replaced by a single Gemini call
that emits the same shape. The shape is the contract — frontend ignores
which side produced it.

Streaming progress is exposed via the async generator `generate_with_progress`
so the wizard's wait-state animation can update its caption line as
generation moves through phases. The captions are deterministic in stub
mode and will become slightly more dynamic once Gemini drives them.
"""
from __future__ import annotations

import asyncio
import re
import textwrap
from typing import AsyncIterator, Dict, List, Optional, Tuple

import yaml

from app.schemas.onboarding import (
    AppPreview,
    GeneratedConfig,
    OnboardingAnswers,
    PersonaPoolPreview,
    PersonaPreview,
    SurfacePreview,
    TaxonomyEdgePreview,
    TaxonomyNodePreview,
    TaxonomyPreview,
)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


async def generate(answers: OnboardingAnswers) -> GeneratedConfig:
    """One-shot generation; collapses the async iterator into a final value."""
    final: Optional[GeneratedConfig] = None
    async for event in generate_with_progress(answers):
        if event[0] == "done":
            final = event[1]
    if final is None:
        raise RuntimeError("config_generator: no terminal 'done' event emitted")
    return final


async def generate_with_progress(
    answers: OnboardingAnswers,
) -> AsyncIterator[Tuple[str, object]]:
    """Yields progress events suitable for SSE streaming.

    Event shape: (kind, payload)
      ('progress', caption: str)  — caption to display under the wait animation
      ('done', GeneratedConfig)   — terminal event with the generated config
      ('error', str)              — terminal event on failure
    """
    try:
        yield ("progress", f"Reading your answers about {_domain_phrase(answers)}…")
        await asyncio.sleep(0.4)  # tiny breath so the caption is visible

        yield ("progress", "Picking advisors for your roundtable…")
        cofounder_pool, research_pool = _generate_persona_pools(answers)
        await asyncio.sleep(0.4)

        yield ("progress", "Naming the things you care about…")
        taxonomy = _generate_taxonomy(answers)
        await asyncio.sleep(0.4)

        yield ("progress", "Choosing your surfaces…")
        surfaces, enabled_ids = _generate_surfaces(answers)
        await asyncio.sleep(0.3)

        yield ("progress", "Tuning prompts for your stage…")
        worklog_templates = _generate_worklog_templates(answers)
        await asyncio.sleep(0.3)

        yield ("progress", "Assembling your workbench…")
        app = AppPreview(
            name="WorkspaceOS",
            tagline=_tagline_for(answers),
            accent="#7c3aed",
        )

        raw_files = _emit_raw_files(
            app=app,
            surfaces=surfaces,
            enabled_ids=enabled_ids,
            cofounder_pool=cofounder_pool,
            research_pool=research_pool,
            taxonomy=taxonomy,
            worklog_templates=worklog_templates,
        )

        config = GeneratedConfig(
            app=app,
            surfaces=surfaces,
            persona_pools=[cofounder_pool, research_pool],
            taxonomy=taxonomy,
            worklog_templates=worklog_templates,
            raw_files=raw_files,
        )

        yield ("done", config)
    except Exception as exc:  # pragma: no cover — defensive guard
        yield ("error", str(exc))


# ---------------------------------------------------------------------------
# Deterministic stub helpers (replaced by a Gemini call in phase 2)
# ---------------------------------------------------------------------------


def _domain_phrase(answers: OnboardingAnswers) -> str:
    """Shortens domain text for caption use."""
    d = answers.domain.strip()
    return d if len(d) <= 40 else d[:37].rstrip() + "…"


def _tagline_for(answers: OnboardingAnswers) -> str:
    audience = ", ".join(answers.audience[:2]) if answers.audience else "builders"
    return f"AI co-founder for {audience.replace('_', ' ')}"


# Famous-figure persona templates per domain bucket. Phase 2 replaces this
# with LLM inference, but having shape-correct stub data lets the wizard
# UI ship and demo without API keys configured.
_DOMAIN_BUCKETS: Dict[str, Tuple[List[Tuple[str, str, str, str]], List[Tuple[str, str, str, str]]]] = {
    "computer science": (
        # cofounder pool: (id, name, color, system_prompt)
        [
            ("yc", "YC Partner", "#3b82f6", "You apply YC interview rigor to {domain} startups."),
            ("musk", "Elon Musk", "#f97316", "You reason from first principles about {domain}."),
            ("hormozi", "Alex Hormozi", "#10b981", "You evaluate offer + market in {domain}."),
            ("dan-koe", "Dan Koe", "#a855f7", "You think about one-person businesses in {domain}."),
        ],
        # research pool: (id, name, color, system_prompt)
        [
            ("bengio", "Yoshua Bengio", "#ef4444", "You critique technical rigor in {domain}."),
            ("lecun", "Yann LeCun", "#3b82f6", "You push on novelty and positioning in {domain}."),
            ("pinker", "Steven Pinker", "#a855f7", "You sharpen writing clarity in {domain}."),
            ("ng", "Andrew Ng", "#10b981", "You demand practical impact in {domain}."),
            ("xie", "Saining Xie", "#f97316", "You evaluate design elegance in {domain}."),
            ("topol", "Eric Topol", "#ec4899", "You ground claims in real-world evidence for {domain}."),
        ],
    ),
    "biology": (
        [
            ("a16z-bio", "a16z Bio Partner", "#3b82f6", "You assess biotech market opportunity in {domain}."),
            ("flagship", "Flagship Pioneering", "#10b981", "You shape biotech company creation in {domain}."),
            ("doudna-ops", "Operator-Scientist", "#a855f7", "You bridge wet lab and commercial in {domain}."),
        ],
        [
            ("doudna", "Jennifer Doudna", "#ef4444", "You critique molecular rigor in {domain}."),
            ("topol", "Eric Topol", "#3b82f6", "You ground claims in clinical evidence for {domain}."),
            ("collins", "Francis Collins", "#a855f7", "You evaluate scientific clarity in {domain}."),
            ("zhang", "Feng Zhang", "#10b981", "You scrutinize technique and reproducibility in {domain}."),
            ("varmus", "Harold Varmus", "#f97316", "You push on biological significance in {domain}."),
        ],
    ),
    "economics": (
        [
            ("first-round", "First Round Partner", "#3b82f6", "You evaluate market timing in {domain}."),
            ("sequoia-ops", "Sequoia Partner", "#10b981", "You stress-test the moat in {domain}."),
            ("hormozi", "Alex Hormozi", "#a855f7", "You analyze unit economics in {domain}."),
        ],
        [
            ("acemoglu", "Daron Acemoglu", "#ef4444", "You critique institutional reasoning in {domain}."),
            ("duflo", "Esther Duflo", "#3b82f6", "You demand rigorous identification in {domain}."),
            ("krugman", "Paul Krugman", "#a855f7", "You sharpen exposition for general audiences in {domain}."),
            ("piketty", "Thomas Piketty", "#10b981", "You probe long-run dynamics in {domain}."),
            ("athey", "Susan Athey", "#f97316", "You evaluate causal methodology in {domain}."),
        ],
    ),
}


def _bucket_for(domain: str) -> str:
    """Crude domain → bucket mapping until Gemini handles it.

    Falls back to 'computer science' for unmatched text so the wizard
    always returns something rather than erroring.
    """
    d = domain.lower()
    if any(k in d for k in ("bio", "medicine", "health", "clinical", "neuro", "genomic")):
        return "biology"
    if any(k in d for k in ("econ", "finance", "market", "trade", "policy")):
        return "economics"
    return "computer science"


def _generate_persona_pools(
    answers: OnboardingAnswers,
) -> Tuple[PersonaPoolPreview, PersonaPoolPreview]:
    bucket = _bucket_for(answers.domain)
    cofounder_seeds, research_seeds = _DOMAIN_BUCKETS[bucket]
    domain_clean = answers.domain.strip()

    cofounder = PersonaPoolPreview(
        pool_id="cofounder",
        label="Co-Founder",
        mode_label="Co-Founder",
        personas=[
            PersonaPreview(
                id=pid,
                name=name,
                color=color,
                system_prompt=prompt.format(domain=domain_clean),
            )
            for pid, name, color, prompt in cofounder_seeds
        ],
    )
    research = PersonaPoolPreview(
        pool_id="research",
        label="Research",
        mode_label="Research",
        personas=[
            PersonaPreview(
                id=pid,
                name=name,
                color=color,
                system_prompt=prompt.format(domain=domain_clean),
            )
            for pid, name, color, prompt in research_seeds
        ],
    )
    return cofounder, research


def _generate_taxonomy(answers: OnboardingAnswers) -> TaxonomyPreview:
    """Default startup taxonomy with optional extension from user text.

    If the user wrote about tracking 'experiments' or 'customer interviews',
    those become node types. Phase 2 lets Gemini pick richer ones.
    """
    base_nodes = [
        TaxonomyNodePreview(id="decision", label="Decision", color="#22c55e",
                            description="A choice made and its rationale"),
        TaxonomyNodePreview(id="claim", label="Claim", color="#3b82f6",
                            description="An assertion the user wants to test"),
        TaxonomyNodePreview(id="hypothesis", label="Hypothesis", color="#a855f7",
                            description="A testable prediction"),
        TaxonomyNodePreview(id="question", label="Question", color="#f97316",
                            description="An open question worth tracking"),
        TaxonomyNodePreview(id="rejection", label="Rejection", color="#ef4444",
                            description="A path explicitly closed"),
        TaxonomyNodePreview(id="blocker", label="Blocker", color="#fb7185",
                            description="A current obstacle"),
        TaxonomyNodePreview(id="insight", label="Insight", color="#eab308",
                            description="A non-obvious realization"),
    ]
    tracked = (answers.tracked_artifacts or "").lower()
    if "experiment" in tracked:
        base_nodes.append(TaxonomyNodePreview(
            id="experiment", label="Experiment", color="#06b6d4",
            description="An experiment with hypothesis + result",
        ))
    if "interview" in tracked or "customer" in tracked:
        base_nodes.append(TaxonomyNodePreview(
            id="interview", label="Interview", color="#14b8a6",
            description="A conversation surfacing user / customer signal",
        ))

    edges = [
        TaxonomyEdgePreview(id="supports", label="supports"),
        TaxonomyEdgePreview(id="contradicts", label="contradicts"),
        TaxonomyEdgePreview(id="refines", label="refines"),
        TaxonomyEdgePreview(id="rejects", label="rejects"),
        TaxonomyEdgePreview(id="related_to", label="related to"),
    ]
    return TaxonomyPreview(name="custom", node_types=base_nodes, edge_types=edges)


_SURFACES_BLUEPRINT: List[Dict[str, str]] = [
    {"type": "roundtable", "id": "cofounder", "letter": "R", "label": "Roundtable", "accent": "violet"},
    {"type": "roundtable", "id": "research", "letter": "A", "label": "Research", "accent": "blue"},
    {"type": "list", "id": "drafts", "letter": "D", "label": "Drafts", "accent": "orange"},
    {"type": "list", "id": "papers", "letter": "P", "label": "Papers", "accent": "blue"},
    {"type": "graph", "id": "knowledge", "letter": "K", "label": "Knowledge", "accent": "teal"},
    {"type": "report", "id": "worklog", "letter": "W", "label": "Worklog", "accent": "emerald"},
]


def _generate_surfaces(
    answers: OnboardingAnswers,
) -> Tuple[List[SurfacePreview], List[str]]:
    """Map outputs/cadence answers to which surfaces are enabled.

    Hard rules:
      - Cofounder roundtable always on (the framework's pivot surface).
      - Knowledge always on (it gets fed automatically from any roundtable).
      - Research roundtable on if user produces papers or audience includes
        peer_researchers.
      - Papers on if user produces papers.
      - Drafts on if user produces blog_posts / social / internal_reports.
      - Worklog on unless cadence == 'none'.
    """
    outputs = set(answers.primary_outputs or [])
    audience = set(answers.audience or [])
    cadence = answers.cadence

    enabled: List[str] = ["cofounder", "knowledge"]
    if "papers" in outputs or "peer_researchers" in audience:
        enabled.append("research")
    if "papers" in outputs:
        enabled.append("papers")
    if outputs & {"blog_posts", "social", "internal_reports"}:
        enabled.append("drafts")
    if cadence and cadence != "none":
        enabled.append("worklog")

    surfaces = [
        SurfacePreview(
            type=s["type"], id=s["id"], letter=s["letter"],
            label=s["label"], accent=s["accent"],
            enabled=(s["id"] in enabled),
        )
        for s in _SURFACES_BLUEPRINT
    ]
    return surfaces, enabled


def _generate_worklog_templates(answers: OnboardingAnswers) -> Dict[str, str]:
    """Return cadence → template prompt text. Empty dict if worklog disabled."""
    if not answers.cadence or answers.cadence == "none":
        return {}
    domain = answers.domain.strip()
    stage_hint = f" The user is in the {answers.stage} stage." if answers.stage else ""
    base = textwrap.dedent(f"""\
        You are writing a {{cadence}} progress report for a {domain} project.
        Use the activity events and knowledge nodes from the period to draft
        a concise narrative — what shipped, what was decided, what's open.
        Format: Markdown with H2 sections (Shipped / Decided / Open).{stage_hint}
    """).strip()
    cadences = ["weekly", "monthly", "quarterly"] if answers.cadence != "none" else []
    return {c: base.replace("{cadence}", c) for c in cadences}


# ---------------------------------------------------------------------------
# Raw YAML emission — what /config/apply writes to disk
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-") or "custom"


def _emit_raw_files(
    *,
    app: AppPreview,
    surfaces: List[SurfacePreview],
    enabled_ids: List[str],
    cofounder_pool: PersonaPoolPreview,
    research_pool: PersonaPoolPreview,
    taxonomy: TaxonomyPreview,
    worklog_templates: Dict[str, str],
) -> Dict[str, str]:
    """Produce the file payloads that /config/apply will write."""
    files: Dict[str, str] = {}

    # personas/cofounder.yaml
    files["personas/cofounder.yaml"] = yaml.safe_dump({
        "pool_id": cofounder_pool.pool_id,
        "label": cofounder_pool.label,
        "mode_label": cofounder_pool.mode_label,
        "personas": [
            {"id": p.id, "name": p.name, "color": p.color, "system_prompt": p.system_prompt}
            for p in cofounder_pool.personas
        ],
    }, sort_keys=False)

    # personas/research.yaml
    files["personas/research.yaml"] = yaml.safe_dump({
        "pool_id": research_pool.pool_id,
        "label": research_pool.label,
        "mode_label": research_pool.mode_label,
        "personas": [
            {"id": p.id, "name": p.name, "color": p.color, "system_prompt": p.system_prompt}
            for p in research_pool.personas
        ],
    }, sort_keys=False)

    # taxonomies/custom.yaml
    files[f"taxonomies/{taxonomy.name}.yaml"] = yaml.safe_dump({
        "name": taxonomy.name,
        "node_types": [
            {"id": n.id, "label": n.label, "color": n.color, **(
                {"description": n.description} if n.description else {})}
            for n in taxonomy.node_types
        ],
        "edge_types": [
            {"id": e.id, **({"label": e.label} if e.label else {})}
            for e in taxonomy.edge_types
        ],
    }, sort_keys=False)

    # prompts/worklog/*.txt
    for cadence, text in worklog_templates.items():
        files[f"prompts/worklog/{cadence}.txt"] = text + "\n"

    # domain.yaml — the entry point the loader reads on startup
    domain_yaml = {
        "app": {
            "name": app.name,
            "tagline": app.tagline,
            "accent": app.accent,
        },
        "surfaces": [
            _surface_yaml_entry(s, taxonomy.name)
            for s in surfaces if s.enabled
        ],
        "integrations": {
            "github": False,
            "google_drive": False,
            "google_gmail": False,
            "outlook": False,
        },
    }
    files["domain.yaml"] = yaml.safe_dump(domain_yaml, sort_keys=False)

    return files


def _surface_yaml_entry(surface: SurfacePreview, taxonomy_name: str) -> Dict[str, object]:
    """Compose one entry in domain.yaml's surfaces list, attaching the right
    nested refs based on surface id."""
    base: Dict[str, object] = {
        "type": surface.type,
        "id": surface.id,
        "letter": surface.letter,
        "label": surface.label,
        "accent": surface.accent,
    }
    if surface.id == "cofounder":
        base["personas"] = "./personas/cofounder.yaml"
        base["extraction"] = {
            "stage1": "./prompts/extraction/stage1-classifier.txt",
            "stage2": "./prompts/extraction/stage2-extractor.txt",
            "taxonomy": f"./taxonomies/{taxonomy_name}.yaml",
        }
    elif surface.id == "research":
        base["personas"] = "./personas/research.yaml"
    elif surface.id == "papers":
        base["paper_types"] = "./prompts/paper/type-hints.yaml"
    elif surface.id == "knowledge":
        base["taxonomy"] = f"./taxonomies/{taxonomy_name}.yaml"
    elif surface.id == "worklog":
        base["templates"] = {
            "weekly": "./prompts/worklog/weekly.txt",
            "monthly": "./prompts/worklog/monthly.txt",
            "quarterly": "./prompts/worklog/quarterly.txt",
        }
    return base
