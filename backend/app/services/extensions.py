"""Extension discovery, loading, and matching.

Extensions live under CONFIG_DIR/extensions/<id>/manifest.yaml. The loader
reads all manifests + their referenced files on first call and caches
them. match_extension(answers) returns the best-scoring extension (or
None) for a given wizard payload.

Score is intentionally simple keyword overlap:
  domain_keywords  → 2 points per hit (substring match, case-insensitive)
  audience_any     → 1 point per overlap with answers.audience
  outputs_any      → 1 point per overlap with answers.primary_outputs

An extension must score >= MATCH_THRESHOLD to be considered a fit. The
threshold is set to require at least one domain keyword hit OR audience
+ output overlap — prevents accidental matches from weak signals.

When an extension matches, its bundled files override the deterministic
stub output. The config_generator splices them into raw_files.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.schemas.extension import ExtensionManifest
from app.schemas.onboarding import OnboardingAnswers

logger = logging.getLogger(__name__)

# Score below which we consider the match insufficient. Tuned so a single
# domain keyword hit (2 pts) crosses; a sole audience overlap (1 pt)
# doesn't.
MATCH_THRESHOLD = 2


def _config_dir() -> Path:
    docker_path = Path("/app/config")
    return docker_path if docker_path.exists() else Path("config")


def _extensions_dir() -> Path:
    return _config_dir() / "extensions"


class LoadedExtension:
    """An extension with its manifest + resolved file contents.

    The file contents (`personas_files`, `taxonomy_extra`,
    `worklog_templates`) are loaded eagerly so config_generator can
    inline them into the GeneratedConfig without further disk IO. Each
    is keyed by the file's relative path inside the active config tree
    (e.g. 'personas/cofounder.yaml'), so they can be written verbatim
    on /config/apply.

    Capability declarations live on `manifest.capabilities`. They are
    Phase 2 — the loader passes them through verbatim but the runtime
    doesn't execute them. Authors can list intended ingest / slash /
    action capabilities now to keep manifests forward-compatible.
    """

    def __init__(
        self,
        manifest: ExtensionManifest,
        folder: Path,
        personas_files: Dict[str, str],
        taxonomy_extra: Optional[str],
        worklog_templates: Dict[str, str],
    ):
        self.manifest = manifest
        self.folder = folder
        self.personas_files = personas_files  # rel-path → yaml text
        self.taxonomy_extra = taxonomy_extra  # yaml text or None
        self.worklog_templates = worklog_templates  # cadence → text

    def __repr__(self) -> str:
        return f"<LoadedExtension {self.manifest.id} v{self.manifest.version}>"


_loaded: Optional[List[LoadedExtension]] = None


def get_all_extensions() -> List[LoadedExtension]:
    """Return loaded extensions, reading from disk on first call."""
    global _loaded
    if _loaded is None:
        _loaded = _discover()
    return _loaded


def reload_extensions() -> None:
    """Force a re-read of the extensions directory. Useful in tests or
    when extensions are added at runtime."""
    global _loaded
    _loaded = None


def _discover() -> List[LoadedExtension]:
    ext_dir = _extensions_dir()
    if not ext_dir.exists():
        logger.info("extensions: %s does not exist — no extensions loaded", ext_dir)
        return []

    result: List[LoadedExtension] = []
    for child in sorted(ext_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.yaml"
        if not manifest_path.exists():
            logger.warning("extensions: skipping %s — no manifest.yaml", child)
            continue
        try:
            ext = _load_one(manifest_path)
            result.append(ext)
            logger.info("extensions: loaded %s", ext.manifest.id)
        except Exception as exc:
            logger.warning("extensions: failed to load %s: %s", child, exc)
    return result


def _load_one(manifest_path: Path) -> LoadedExtension:
    folder = manifest_path.parent
    with open(manifest_path) as f:
        raw = yaml.safe_load(f) or {}
    manifest = ExtensionManifest.model_validate(raw)

    personas_files: Dict[str, str] = {}
    if manifest.personas:
        for pool_id, rel in manifest.personas.items():
            target = (folder / rel).resolve()
            # The destination in the active config tree mirrors the
            # pool_id naming convention.
            personas_files[f"personas/{pool_id}.yaml"] = target.read_text()

    taxonomy_extra: Optional[str] = None
    if manifest.taxonomy_extra:
        target = (folder / manifest.taxonomy_extra).resolve()
        taxonomy_extra = target.read_text()

    worklog_templates: Dict[str, str] = {}
    if manifest.worklog_templates:
        for cadence, rel in manifest.worklog_templates.items():
            target = (folder / rel).resolve()
            worklog_templates[cadence] = target.read_text()

    return LoadedExtension(
        manifest=manifest,
        folder=folder,
        personas_files=personas_files,
        taxonomy_extra=taxonomy_extra,
        worklog_templates=worklog_templates,
    )


def score_extension(ext: LoadedExtension, answers: OnboardingAnswers) -> int:
    """Compute a match score for one extension against wizard answers."""
    score = 0
    domain_lower = answers.domain.lower()
    for kw in ext.manifest.matches.domain_keywords:
        if kw.lower() in domain_lower:
            score += 2
    audience_set = set(answers.audience or [])
    for aud in ext.manifest.matches.audience_any:
        if aud in audience_set:
            score += 1
    output_set = set(answers.primary_outputs or [])
    for out in ext.manifest.matches.outputs_any:
        if out in output_set:
            score += 1
    return score


def match_extension(answers: OnboardingAnswers) -> Optional[LoadedExtension]:
    """Return the best-scoring extension above threshold, or None."""
    candidates = get_all_extensions()
    if not candidates:
        return None
    ranked = sorted(
        ((score_extension(ext, answers), ext) for ext in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best_ext = ranked[0]
    if best_score < MATCH_THRESHOLD:
        return None
    return best_ext
