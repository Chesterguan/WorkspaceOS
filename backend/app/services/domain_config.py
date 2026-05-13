"""Loads domain config files at boot and exposes typed accessors.

Lifecycle:
  - On startup, load_on_startup() reads config/domain.yaml from CONFIG_DIR
  - If missing, copies config/presets/indie-hacker.yaml to domain.yaml
  - Parses + validates against Pydantic schemas
  - Caches in module-level singleton

Path refs (./personas/foo.yaml) are resolved lazily on accessor calls so
broken refs surface at use-time with a clear error, not at startup.
"""
import logging
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.schemas.domain_config import (
    AppConfig, DomainConfig, PaperTypeHint, PersonaPool, SurfaceConfig, Taxonomy,
)

logger = logging.getLogger(__name__)

# Default CONFIG_DIR is the project root's config/ directory. Tests can
# inject a different one via DomainConfigLoader(config_dir=tmp_path).
_DEFAULT_CONFIG_DIR = Path("/app/config") if Path("/app/config").exists() else Path("config")


class DomainConfigLoader:
    """Owns the parsed config tree. Exposes accessors used by services + router."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = Path(config_dir) if config_dir else _DEFAULT_CONFIG_DIR
        self._root: Optional[DomainConfig] = None

    # -- lifecycle -----------------------------------------------------------

    def load(self) -> None:
        """Read + parse + validate. Call once at startup."""
        config_path = self.config_dir / "domain.yaml"
        if not config_path.exists():
            self._install_default_preset(config_path)
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        self._root = DomainConfig.model_validate(raw)
        logger.info(
            "domain_config loaded: app=%s surfaces=%d",
            self._root.app.name, len(self._root.surfaces),
        )

    def _install_default_preset(self, target: Path) -> None:
        preset = self.config_dir / "presets" / "indie-hacker.yaml"
        if not preset.exists():
            raise FileNotFoundError(
                f"No domain config at {target} and no default preset at {preset}. "
                "Cannot start without one of these."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(preset, target)
        logger.info("Installed default preset: %s -> %s", preset, target)

    # -- top-level accessors --------------------------------------------------

    def get_app(self) -> AppConfig:
        return self._require().app

    def get_surfaces(self) -> List[SurfaceConfig]:
        return self._require().surfaces

    def get_integrations(self) -> Dict[str, bool]:
        return dict(self._require().integrations)

    # -- referenced-file accessors -------------------------------------------

    def get_personas(self, pool_id: str) -> PersonaPool:
        """Find the surface with `personas: ./path.yaml` matching pool_id."""
        for s in self.get_surfaces():
            if s.personas:
                pool = self._load_persona_file(s.personas)
                if pool.pool_id == pool_id:
                    return pool
        raise KeyError(f"persona pool {pool_id!r} not found in any surface")

    def get_taxonomy_by_path(self, ref: str) -> Taxonomy:
        return self._load_taxonomy_file(ref)

    def get_taxonomy_for_surface(self, surface_id: str) -> Taxonomy:
        for s in self.get_surfaces():
            if s.id == surface_id and s.taxonomy:
                return self._load_taxonomy_file(s.taxonomy)
        raise KeyError(f"no taxonomy on surface {surface_id!r}")

    def get_paper_type_hints(self) -> Dict[str, PaperTypeHint]:
        for s in self.get_surfaces():
            if s.paper_types:
                path = (self.config_dir / s.paper_types).resolve()
                with open(path) as f:
                    raw = yaml.safe_load(f)
                return {item["id"]: PaperTypeHint.model_validate(item) for item in raw}
        return {}

    def get_worklog_template(self, period: str) -> str:
        for s in self.get_surfaces():
            if s.type == "report" and s.templates:
                template_path = getattr(s.templates, period, None)
                if template_path:
                    path = (self.config_dir / template_path).resolve()
                    return path.read_text()
        raise KeyError(f"no worklog template for period {period!r}")

    def render_prompt(
        self,
        ref: str,
        *,
        taxonomy_path: Optional[str] = None,
        extra_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """Read a prompt file and substitute placeholders.

        Available placeholders:
          - {taxonomy_node_type_ids} — pipe-separated IDs
          - {taxonomy_edge_type_ids} — pipe-separated IDs
          - {taxonomy_summary} — bulleted list of "id: description"
          - anything in extra_vars

        Unknown placeholders are left as literal text (no error).
        """
        path = (self.config_dir / ref).resolve()
        body = path.read_text()
        replacements: Dict[str, str] = dict(extra_vars or {})
        if taxonomy_path:
            tax = self._load_taxonomy_file(taxonomy_path)
            replacements["taxonomy_node_type_ids"] = "|".join(sorted(tax.node_type_ids))
            replacements["taxonomy_edge_type_ids"] = "|".join(sorted(tax.edge_type_ids))
            replacements["taxonomy_summary"] = "\n".join(
                f"- {n.id}: {n.description or n.label}" for n in tax.node_types
            )
        # Replace {key} only when key matches our known set; leave unknowns alone.
        def _sub(match: re.Match) -> str:
            key = match.group(1)
            return replacements.get(key, match.group(0))
        return re.sub(r"\{(\w+)\}", _sub, body)

    # -- internal helpers -----------------------------------------------------

    def _require(self) -> DomainConfig:
        if self._root is None:
            # Lazy-load on first access. Production calls load_on_startup() in
            # the FastAPI lifespan, but tests (and any out-of-band tooling) hit
            # services without that hook — auto-loading keeps them working with
            # the same config the running server uses.
            self.load()
        if self._root is None:
            raise RuntimeError("domain_config failed to load")
        return self._root

    def _load_persona_file(self, ref: str) -> PersonaPool:
        path = (self.config_dir / ref).resolve()
        with open(path) as f:
            return PersonaPool.model_validate(yaml.safe_load(f))

    def _load_taxonomy_file(self, ref: str) -> Taxonomy:
        path = (self.config_dir / ref).resolve()
        with open(path) as f:
            return Taxonomy.model_validate(yaml.safe_load(f))


# Module-level singleton (constructed lazily)
_loader: Optional[DomainConfigLoader] = None


def get_loader() -> DomainConfigLoader:
    global _loader
    if _loader is None:
        _loader = DomainConfigLoader()
    return _loader


def load_on_startup() -> None:
    """Call from app startup (in main.py) before any service uses config."""
    get_loader().load()
