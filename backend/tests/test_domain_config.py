import pytest
from app.schemas.domain_config import (
    AppConfig, Persona, PersonaPool, NodeTypeDef, EdgeTypeDef,
    Taxonomy, SurfaceConfig,
)


def test_app_config_minimal():
    app = AppConfig(name="ProjectScribe", accent="#7c3aed")
    assert app.name == "ProjectScribe"
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
