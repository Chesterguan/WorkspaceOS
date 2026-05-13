"""Serve the active domain config to the frontend.

Exposes the loaded config/domain.yaml in a resolved + denormalized shape so
the bench UI can render the rail, advisor pickers, and taxonomy palettes
without follow-up calls.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.dependencies import verify_api_key
from app.services.domain_config import get_loader

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/domain")
async def get_domain_config(_: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Return the active domain config with taxonomies + persona pools inlined."""
    loader = get_loader()
    surfaces: List[Dict[str, Any]] = []
    for s in loader.get_surfaces():
        surface_dict: Dict[str, Any] = {
            "type": s.type,
            "id": s.id,
            "letter": s.letter,
            "label": s.label,
            "accent": s.accent,
        }
        if s.taxonomy:
            tax = loader.get_taxonomy_by_path(s.taxonomy)
            surface_dict["taxonomy"] = {
                "node_types": [n.model_dump() for n in tax.node_types],
                "edge_types": [e.model_dump() for e in tax.edge_types],
            }
        if s.personas:
            pool = loader._load_persona_file(s.personas)
            surface_dict["personas"] = {
                "pool_id": pool.pool_id,
                "mode_label": pool.mode_label,
                "items": [
                    {"id": p.id, "name": p.name, "color": p.color, "avatar": p.avatar}
                    for p in pool.personas
                ],
            }
        surfaces.append(surface_dict)

    app_cfg = loader.get_app()
    return {
        "app": {
            "name": app_cfg.name,
            "accent": app_cfg.accent,
            "tagline": app_cfg.tagline,
        },
        "surfaces": surfaces,
        "integrations": loader.get_integrations(),
    }
