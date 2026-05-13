"""Generates a domain config from onboarding wizard answers.

Phase 1: deterministic stub keyed off a tiny domain → bucket table.
Phase 2 (this file now): real Gemini call. The LLM produces the creative
fragments (personas + tagline + taxonomy extensions); deterministic Python
owns the structural decisions (which surfaces to enable, base taxonomy
nodes, file layout). Cleanest split — the LLM can't accidentally break
the bench by emitting an unknown surface type.

Streaming progress is exposed via the async generator
`generate_with_progress` so the wizard's wait-state animation can update
its caption line. The same events also get pushed into the global event
stream (`emit`), so the bench log shows the work after the user
navigates back.

If GEMINI_API_KEY is missing or the LLM call fails, we fall back to the
deterministic bucket logic — keeps the demo deployment usable without
keys.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import textwrap
from typing import AsyncIterator, Dict, List, Optional, Tuple

import yaml

from app.config import settings
from app.schemas.onboarding import (
    AppPreview,
    ExtensionBadge,
    GeneratedConfig,
    OnboardingAnswers,
    PersonaPoolPreview,
    PersonaPreview,
    SurfacePreview,
    TaxonomyEdgePreview,
    TaxonomyNodePreview,
    TaxonomyPreview,
)
from app.services import extensions as ext_service
from app.services.ai_client import get_cloud_client
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


async def generate(answers: OnboardingAnswers) -> GeneratedConfig:
    """One-shot generation; collapses the async iterator into a final value."""
    final: Optional[GeneratedConfig] = None
    async for event in generate_with_progress(answers):
        if event[0] == "done":
            final = event[1]  # type: ignore[assignment]
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
    domain_phrase = _domain_phrase(answers)
    emit("info", "wizard", f"Generating workbench for {domain_phrase}")

    try:
        # ── Phase A: extension match → LLM → stub ─────────────────────────
        yield ("progress", f"Reading your answers about {domain_phrase}…")
        emit("info", "wizard", f"Wizard: reading answers ({domain_phrase})")
        await asyncio.sleep(0.2)

        matched_extension = ext_service.match_extension(answers)
        extension_badge: Optional[ExtensionBadge] = None
        prebaked_files: Dict[str, str] = {}

        if matched_extension is not None:
            yield ("progress", f"Matched the {matched_extension.manifest.name} extension…")
            score = ext_service.score_extension(matched_extension, answers)
            emit(
                "success", "wizard",
                f"Matched extension: {matched_extension.manifest.name} (score {score})",
                meta={"extension_id": matched_extension.manifest.id, "score": score},
            )
            extension_badge = ExtensionBadge(
                id=matched_extension.manifest.id,
                name=matched_extension.manifest.name,
                version=matched_extension.manifest.version,
                description=matched_extension.manifest.description,
                score=score,
            )
            llm_pack = _pack_from_extension(matched_extension, answers)
            prebaked_files = dict(matched_extension.personas_files)
            for cadence, text in matched_extension.worklog_templates.items():
                prebaked_files[f"prompts/worklog/{cadence}.txt"] = text
        else:
            use_llm = bool(settings.gemini_api_key) and not _force_stub()
            if use_llm:
                yield ("progress", "No extension match — asking Gemini to pick your panel…")
                try:
                    llm_pack = await _generate_with_llm(answers)
                    emit("success", "wizard", "LLM picked personas + taxonomy extensions")
                except Exception as exc:
                    logger.warning("config_generator: LLM call failed (%s) — falling back to stub", exc)
                    emit("warn", "wizard", f"LLM call failed: {exc}. Using bucket fallback.")
                    llm_pack = _stub_pack(answers)
            else:
                yield ("progress", "Picking advisors for your roundtable…")
                llm_pack = _stub_pack(answers)
                emit("info", "wizard", "No extension match and no GEMINI_API_KEY — using bucket fallback")

        cofounder_pool, research_pool = llm_pack["cofounder"], llm_pack["research"]
        extra_nodes = llm_pack["taxonomy_additions"]
        tagline_override = llm_pack.get("tagline")

        # ── Phase B: deterministic assembly ────────────────────────────────
        yield ("progress", "Naming the things you care about…")
        taxonomy = _build_taxonomy(answers, extra_nodes)
        await asyncio.sleep(0.2)

        yield ("progress", "Choosing your surfaces…")
        surfaces, enabled_ids = _build_surfaces(answers)
        await asyncio.sleep(0.2)

        yield ("progress", "Tuning prompts for your stage…")
        worklog_templates = _build_worklog_templates(answers)
        await asyncio.sleep(0.2)

        yield ("progress", "Assembling your workbench…")
        app = AppPreview(
            name="WorkspaceOS",
            tagline=tagline_override or _default_tagline(answers),
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
        # When an extension matched, prefer the extension's verbatim files
        # for persona pools and worklog prompts. This preserves the curator's
        # intended formatting + commentary instead of round-tripping through
        # our YAML serializer.
        raw_files.update(prebaked_files)

        config = GeneratedConfig(
            app=app,
            surfaces=surfaces,
            persona_pools=[cofounder_pool, research_pool],
            taxonomy=taxonomy,
            worklog_templates=worklog_templates,
            extension=extension_badge,
            raw_files=raw_files,
        )

        emit(
            "success", "wizard",
            f"Workbench generated: {len(cofounder_pool.personas) + len(research_pool.personas)} personas, "
            f"{len(taxonomy.node_types)} taxonomy nodes, {len(enabled_ids)} surfaces",
        )
        yield ("done", config)

    except Exception as exc:
        logger.exception("config_generator failed")
        emit("error", "wizard", f"Generation failed: {exc}")
        yield ("error", str(exc))


# ---------------------------------------------------------------------------
# LLM creative pass
# ---------------------------------------------------------------------------


def _force_stub() -> bool:
    """Escape hatch — set FORCE_WIZARD_STUB=true to skip the LLM call.
    Useful for tests and demos where you want deterministic personas."""
    return os.getenv("FORCE_WIZARD_STUB", "").lower() in ("1", "true", "yes")


_LLM_SYSTEM_PROMPT = """You are configuring a developer workbench called \
WorkspaceOS for a single user. Given their domain and goals, you pick \
the *people* who would be most valuable to have in their corner — both \
business advisors (for a "Co-Founder" roundtable) and academic / domain \
reviewers (for a "Research" roundtable).

Your response MUST be a single JSON object, no prose, no markdown fences, \
no leading or trailing whitespace. The schema is strict:

{
  "tagline": "<one short phrase, max 10 words, ends without a period>",
  "cofounder_personas": [
    {
      "id": "<short snake_case identifier>",
      "name": "<famous person OR descriptive archetype, max 24 chars>",
      "color": "<hex color #rrggbb, accent for this persona>",
      "system_prompt": "<2-3 sentences describing the lens this persona brings, written in 2nd person addressing the AI>"
    }
  ],
  "research_personas": [...same shape...],
  "taxonomy_additions": [
    {
      "id": "<snake_case>",
      "label": "<human-friendly label, max 18 chars>",
      "color": "<hex>",
      "description": "<one sentence describing what gets tracked under this node type>"
    }
  ]
}

Rules:
- Pick 3-4 cofounder_personas and 5-6 research_personas. No more.
- Cofounder personas: business / strategy / operations / growth lenses. Real \
investors and operators are fine (a16z partners, Sequoia, Hormozi, etc.), \
but if there's a famous *operator* in this exact domain, prefer them.
- Research personas: real domain experts. For a biofoundry, that's people \
like Drew Endy, George Church, Jay Keasling, Tim Lu, Jason Kelly. For \
medical imaging, it's people who actually work on that. Avoid generic \
"AI/ML" figures unless the domain is actually AI/ML.
- Color hex codes should be visually distinct from each other in each pool. \
Use rich tailwind-flavored colors (#3b82f6, #10b981, #a855f7, #f97316, \
#ec4899, #ef4444, #06b6d4, #eab308, etc.). Do not use grayscale.
- taxonomy_additions ADD to a base taxonomy that already has: decision, \
claim, hypothesis, question, rejection, blocker, insight. Only add nodes \
the user explicitly hinted at in their tracked_artifacts text (experiments, \
interviews, metrics, decisions, etc.). 0-4 additions, no duplicates.
- Persona system_prompts should reference the user's specific domain. \
Don't write "you critique research" — write "you critique molecular \
rigor in <their domain>" or similar.
- ID values are stable handles — use ASCII snake_case, derive from name."""


def _llm_user_prompt(answers: OnboardingAnswers) -> str:
    return textwrap.dedent(f"""\
        Domain: {answers.domain}

        Primary outputs: {', '.join(answers.primary_outputs) or '(none specified)'}
        Audience: {', '.join(answers.audience) or '(none specified)'}
        Stage: {answers.stage or '(not specified)'}

        User's dream advisor panel description:
        {answers.advisor_panel or '(let you pick)'}

        What they want to track over time:
        {answers.tracked_artifacts or '(let you pick from base set)'}

        Worklog cadence: {answers.cadence or '(none)'}

        Generate the JSON config now.""")


async def _generate_with_llm(answers: OnboardingAnswers) -> Dict[str, object]:
    """Call Gemini, parse + validate the JSON, normalize to internal shapes.

    Raises if anything goes wrong — caller falls back to stub on exception.
    """
    client = get_cloud_client()
    user = _llm_user_prompt(answers)
    raw = await client.complete(_LLM_SYSTEM_PROMPT, user)
    data = _parse_llm_json(raw)
    return _normalize_llm_pack(data, answers)


def _parse_llm_json(raw: str) -> Dict[str, object]:
    """Tolerant JSON parse — strips markdown fences if the model added them."""
    text = raw.strip()
    if text.startswith("```"):
        # Remove opening fence (with or without language tag)
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        if text.endswith("```"):
            text = text[:-3].rstrip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"LLM returned non-object: {type(data).__name__}")
    return data


def _normalize_llm_pack(data: Dict[str, object], answers: OnboardingAnswers) -> Dict[str, object]:
    """Validate + coerce LLM output into internal pydantic shapes."""
    def _personas(field: str, pool_id: str, label: str) -> PersonaPoolPreview:
        raw_items = data.get(field) or []
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError(f"LLM missing or empty {field}")
        personas: List[PersonaPreview] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            personas.append(PersonaPreview(
                id=_slug(str(raw.get("id") or raw.get("name") or "persona")),
                name=str(raw.get("name") or "Unnamed")[:60],
                color=_normalize_color(str(raw.get("color") or "#7c3aed")),
                system_prompt=str(raw.get("system_prompt") or "").strip()
                              or f"You advise on {answers.domain}.",
            ))
        if not personas:
            raise ValueError(f"LLM {field} had no parseable entries")
        return PersonaPoolPreview(
            pool_id=pool_id, label=label, mode_label=label, personas=personas,
        )

    cofounder = _personas("cofounder_personas", "cofounder", "Co-Founder")
    research = _personas("research_personas", "research", "Research")

    extra_nodes: List[TaxonomyNodePreview] = []
    for raw in (data.get("taxonomy_additions") or []):
        if not isinstance(raw, dict):
            continue
        try:
            extra_nodes.append(TaxonomyNodePreview(
                id=_slug(str(raw.get("id") or raw.get("label") or "extra")),
                label=str(raw.get("label") or "Extra")[:30],
                color=_normalize_color(str(raw.get("color") or "#06b6d4")),
                description=(str(raw.get("description")) if raw.get("description") else None),
            ))
        except Exception:
            continue

    tagline = data.get("tagline")
    return {
        "cofounder": cofounder,
        "research": research,
        "taxonomy_additions": extra_nodes,
        "tagline": (str(tagline)[:80] if tagline else None),
    }


def _normalize_color(s: str) -> str:
    """Coerce to a valid #rrggbb. Defaults to violet if unparseable."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", s.strip())
    if not m:
        return "#7c3aed"
    hex_part = m.group(1)
    if len(hex_part) == 3:
        hex_part = "".join(c * 2 for c in hex_part)
    return "#" + hex_part.lower()


# ---------------------------------------------------------------------------
# Stub fallback — same shape as _normalize_llm_pack
# ---------------------------------------------------------------------------


_DOMAIN_BUCKETS: Dict[str, Tuple[List[Tuple[str, str, str, str]], List[Tuple[str, str, str, str]]]] = {
    "computer science": (
        [
            ("yc", "YC Partner", "#3b82f6", "You apply YC interview rigor to {domain} startups."),
            ("musk", "Elon Musk", "#f97316", "You reason from first principles about {domain}."),
            ("hormozi", "Alex Hormozi", "#10b981", "You evaluate offer + market in {domain}."),
            ("dan-koe", "Dan Koe", "#a855f7", "You think about one-person businesses in {domain}."),
        ],
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
    d = domain.lower()
    if any(k in d for k in ("bio", "medicine", "health", "clinical", "neuro", "genomic")):
        return "biology"
    if any(k in d for k in ("econ", "finance", "market", "trade", "policy")):
        return "economics"
    return "computer science"


def _pack_from_extension(
    ext: "ext_service.LoadedExtension",
    answers: OnboardingAnswers,
) -> Dict[str, object]:
    """Build the same pack shape from a matched extension's bundled files."""
    def _parse_pool(yaml_text: str, default_pool_id: str, default_label: str) -> PersonaPoolPreview:
        raw = yaml.safe_load(yaml_text) or {}
        personas = []
        for p in raw.get("personas") or []:
            personas.append(PersonaPreview(
                id=str(p.get("id") or "unknown"),
                name=str(p.get("name") or "Unnamed")[:60],
                color=str(p.get("color") or "#7c3aed"),
                system_prompt=str(p.get("system_prompt") or "").strip(),
            ))
        return PersonaPoolPreview(
            pool_id=str(raw.get("pool_id") or default_pool_id),
            label=str(raw.get("label") or default_label),
            mode_label=str(raw.get("mode_label") or raw.get("label") or default_label),
            personas=personas,
        )

    cofounder_text = ext.personas_files.get("personas/cofounder.yaml") or ""
    research_text = ext.personas_files.get("personas/research.yaml") or ""
    cofounder = _parse_pool(cofounder_text, "cofounder", "Co-Founder")
    research = _parse_pool(research_text, "research", "Research")

    extra_nodes: List[TaxonomyNodePreview] = []
    if ext.taxonomy_extra:
        raw_tax = yaml.safe_load(ext.taxonomy_extra) or {}
        for n in raw_tax.get("node_types") or []:
            try:
                extra_nodes.append(TaxonomyNodePreview(
                    id=str(n.get("id") or "extra"),
                    label=str(n.get("label") or "Extra")[:30],
                    color=str(n.get("color") or "#06b6d4"),
                    description=(str(n.get("description")) if n.get("description") else None),
                ))
            except Exception:
                continue
    return {
        "cofounder": cofounder,
        "research": research,
        "taxonomy_additions": extra_nodes,
        "tagline": None,
    }


def _stub_pack(answers: OnboardingAnswers) -> Dict[str, object]:
    bucket = _bucket_for(answers.domain)
    cof_seeds, res_seeds = _DOMAIN_BUCKETS[bucket]
    domain = answers.domain.strip()

    def _pool(seeds, pool_id, label):
        return PersonaPoolPreview(
            pool_id=pool_id, label=label, mode_label=label,
            personas=[
                PersonaPreview(
                    id=pid, name=name, color=color,
                    system_prompt=prompt.format(domain=domain),
                )
                for pid, name, color, prompt in seeds
            ],
        )

    extra_nodes: List[TaxonomyNodePreview] = []
    tracked = (answers.tracked_artifacts or "").lower()
    if "experiment" in tracked:
        extra_nodes.append(TaxonomyNodePreview(
            id="experiment", label="Experiment", color="#06b6d4",
            description="An experiment with hypothesis + result",
        ))
    if "interview" in tracked or "customer" in tracked:
        extra_nodes.append(TaxonomyNodePreview(
            id="interview", label="Interview", color="#14b8a6",
            description="A conversation surfacing user / customer signal",
        ))

    return {
        "cofounder": _pool(cof_seeds, "cofounder", "Co-Founder"),
        "research": _pool(res_seeds, "research", "Research"),
        "taxonomy_additions": extra_nodes,
        "tagline": None,
    }


# ---------------------------------------------------------------------------
# Deterministic structure (taxonomy base, surfaces, worklog templates)
# ---------------------------------------------------------------------------


def _domain_phrase(answers: OnboardingAnswers) -> str:
    d = answers.domain.strip()
    return d if len(d) <= 40 else d[:37].rstrip() + "…"


def _default_tagline(answers: OnboardingAnswers) -> str:
    audience = ", ".join(answers.audience[:2]) if answers.audience else "builders"
    return f"AI co-founder for {audience.replace('_', ' ')}"


def _build_taxonomy(
    answers: OnboardingAnswers,
    extra_nodes: List[TaxonomyNodePreview],
) -> TaxonomyPreview:
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
    # Dedupe extras by id against base
    base_ids = {n.id for n in base_nodes}
    for extra in extra_nodes:
        if extra.id not in base_ids:
            base_nodes.append(extra)
            base_ids.add(extra.id)

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


def _build_surfaces(
    answers: OnboardingAnswers,
) -> Tuple[List[SurfacePreview], List[str]]:
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


def _build_worklog_templates(answers: OnboardingAnswers) -> Dict[str, str]:
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
    return {c: base.replace("{cadence}", c) for c in ("weekly", "monthly", "quarterly")}


# ---------------------------------------------------------------------------
# Raw YAML emission
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
    files: Dict[str, str] = {}

    files["personas/cofounder.yaml"] = yaml.safe_dump({
        "pool_id": cofounder_pool.pool_id,
        "label": cofounder_pool.label,
        "mode_label": cofounder_pool.mode_label,
        "personas": [
            {"id": p.id, "name": p.name, "color": p.color, "system_prompt": p.system_prompt}
            for p in cofounder_pool.personas
        ],
    }, sort_keys=False)

    files["personas/research.yaml"] = yaml.safe_dump({
        "pool_id": research_pool.pool_id,
        "label": research_pool.label,
        "mode_label": research_pool.mode_label,
        "personas": [
            {"id": p.id, "name": p.name, "color": p.color, "system_prompt": p.system_prompt}
            for p in research_pool.personas
        ],
    }, sort_keys=False)

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

    for cadence, text in worklog_templates.items():
        files[f"prompts/worklog/{cadence}.txt"] = text + "\n"

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
