import textwrap
from pathlib import Path

import pytest

from app.schemas.domain_config import (
    AppConfig, Persona, PersonaPool, NodeTypeDef, EdgeTypeDef,
    Taxonomy, SurfaceConfig,
)
from app.services.domain_config import DomainConfigLoader


def test_app_config_minimal():
    app = AppConfig(name="WorkspaceOS", accent="#7c3aed")
    assert app.name == "WorkspaceOS"
    assert app.tagline is None


def test_persona_pool_resolves_pool_id_required():
    pool = PersonaPool(
        pool_id="cofounder",
        label="Co-Founder",
        mode_label="Co-Founder",
        personas=[
            Persona(id="yc", name="YC", color="#3b82f6", system_prompt="..."),
        ],
    )
    assert len(pool.personas) == 1
    assert pool.routing.strategy == "smart_select"  # default


def test_taxonomy_node_type_ids_property():
    tax = Taxonomy(
        name="startup",
        node_types=[
            NodeTypeDef(id="decision", label="Decision", color="#22c55e"),
            NodeTypeDef(id="claim", label="Claim", color="#3b82f6"),
        ],
        edge_types=[EdgeTypeDef(id="supports")],
    )
    assert tax.node_type_ids == {"decision", "claim"}
    assert tax.edge_type_ids == {"supports"}


def test_surface_config_supports_known_types():
    s = SurfaceConfig(
        type="roundtable", id="cofounder", letter="R",
        label="Roundtable", accent="violet",
        personas="./personas/cofounder.yaml",
    )
    assert s.type == "roundtable"


def test_surface_config_rejects_unknown_type():
    with pytest.raises(ValueError):
        SurfaceConfig(
            type="alien", id="x", letter="X",
            label="X", accent="violet",
        )


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip())


@pytest.fixture
def fake_config(tmp_path):
    """Build a minimal config tree under tmp_path."""
    base = tmp_path
    _write(base / "personas/cofounder.yaml", """
        pool_id: cofounder
        label: "Co-Founder"
        mode_label: "Co-Founder"
        personas:
          - id: yc
            name: "YC"
            color: "#3b82f6"
            system_prompt: "You are a YC partner."
    """)
    _write(base / "taxonomies/startup.yaml", """
        name: startup
        node_types:
          - id: decision
            label: "Decision"
            color: "#22c55e"
            description: "A choice made"
        edge_types:
          - id: supports
            label: "supports"
    """)
    _write(base / "prompts/extraction/stage2.txt",
           "Use these node types: {taxonomy_node_type_ids}\n\nDetails:\n{taxonomy_summary}")
    _write(base / "domain.yaml", """
        app:
          name: "TestApp"
          accent: "#7c3aed"
        surfaces:
          - type: roundtable
            id: cofounder
            letter: R
            label: "Roundtable"
            accent: violet
            personas: ./personas/cofounder.yaml
            extraction:
              stage2: ./prompts/extraction/stage2.txt
              taxonomy: ./taxonomies/startup.yaml
        integrations:
          github: false
    """)
    return base


def test_loader_reads_domain_yaml(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    app = loader.get_app()
    assert app.name == "TestApp"


def test_loader_resolves_persona_refs(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    pool = loader.get_personas("cofounder")
    assert pool.pool_id == "cofounder"
    assert pool.personas[0].id == "yc"


def test_loader_resolves_taxonomy_refs(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    tax = loader.get_taxonomy_by_path("./taxonomies/startup.yaml")
    assert "decision" in tax.node_type_ids
    assert "supports" in tax.edge_type_ids


def test_loader_substitutes_placeholders(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    surface = loader.get_surfaces()[0]
    rendered = loader.render_prompt(
        surface.extraction.stage2,
        taxonomy_path=surface.extraction.taxonomy,
    )
    assert "decision" in rendered
    assert "{taxonomy_node_type_ids}" not in rendered
    assert "{taxonomy_summary}" not in rendered


def test_loader_unknown_placeholder_left_literal(fake_config):
    # An unknown placeholder is left as-is (no template error).
    bad_prompt = fake_config / "prompts/extraction/stage2.txt"
    bad_prompt.write_text("Hello {unknown_thing}")
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    surface = loader.get_surfaces()[0]
    rendered = loader.render_prompt(
        surface.extraction.stage2,
        taxonomy_path=surface.extraction.taxonomy,
    )
    assert "{unknown_thing}" in rendered  # untouched
