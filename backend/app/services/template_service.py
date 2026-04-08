"""
LaTeX template fetcher: downloads and caches venue-specific templates.

Known venues have official template URLs. For unknown venues, falls back to
standard article class. Templates are cached in backend_data/templates/
(Docker volume) so they persist across restarts.
"""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

TEMPLATE_CACHE_DIR = Path(os.environ.get(
    "TEMPLATE_CACHE_DIR", "/app/backend_data/templates"
))

# Known venue template sources
# Each entry: {template_id: {urls: [download URLs], documentclass: str, packages: str}}
KNOWN_TEMPLATES: Dict[str, Dict] = {
    "neurips": {
        "urls": ["https://media.neurips.cc/Conferences/NeurIPS2024/Styles/neurips_2024.sty"],
        "documentclass": "\\documentclass{article}",
        "packages": (
            "\\usepackage[final]{neurips_2024}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{booktabs}"
        ),
        "files": ["neurips_2024.sty"],
    },
    "icml": {
        "urls": ["https://media.icml.cc/Conferences/ICML2024/Styles/icml2024.sty"],
        "documentclass": "\\documentclass{article}",
        "packages": (
            "\\usepackage{icml2024}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{booktabs}"
        ),
        "files": ["icml2024.sty"],
    },
    "iclr": {
        "urls": [],
        "documentclass": "\\documentclass{article}",
        "packages": (
            "\\usepackage{iclr2025_conference}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}"
        ),
        "files": ["iclr2025_conference.sty"],
    },
    "acl": {
        "urls": [],
        "documentclass": "\\documentclass[11pt]{article}",
        "packages": (
            "\\usepackage{acl}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}"
        ),
        "files": ["acl.sty"],
    },
    "aaai": {
        "urls": [],
        "documentclass": "\\documentclass[letterpaper]{article}",
        "packages": (
            "\\usepackage{aaai24}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}"
        ),
        "files": ["aaai24.sty"],
    },
    "arxiv": {
        "urls": [],
        "documentclass": "\\documentclass[12pt]{article}",
        "packages": (
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{setspace}\n"
            "\\doublespacing"
        ),
        "files": [],
    },
    "ieee": {
        "urls": [],
        "documentclass": "\\documentclass[conference]{IEEEtran}",
        "packages": (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb,amsfonts}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}"
        ),
        "files": [],
    },
    "acm": {
        "urls": [],
        "documentclass": "\\documentclass[sigconf]{acmart}",
        "packages": (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{hyperref}"
        ),
        "files": [],
    },
}


def _match_template(venue_name: str) -> Optional[str]:
    """Match a venue name to a known template ID (case-insensitive substring)."""
    if not venue_name:
        return None
    lower = venue_name.lower()
    for key in KNOWN_TEMPLATES:
        if key in lower:
            return key
    return None


async def fetch_template_files(template_id: str) -> bool:
    """Download template files for a known venue if not already cached.

    Returns True if files are available (cached or just downloaded).
    """
    tmpl = KNOWN_TEMPLATES.get(template_id)
    if not tmpl or not tmpl["urls"]:
        return True  # No files to download (built-in template)

    TEMPLATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for url in tmpl["urls"]:
        filename = url.split("/")[-1]
        filepath = TEMPLATE_CACHE_DIR / filename

        if filepath.exists():
            logger.debug("template_service: %s already cached", filename)
            continue

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    filepath.write_bytes(resp.content)
                    logger.info("template_service: downloaded %s", filename)
                else:
                    logger.warning(
                        "template_service: failed to download %s (HTTP %d)",
                        url, resp.status_code,
                    )
                    return False
        except Exception:
            logger.exception("template_service: error downloading %s", url)
            return False

    return True


def get_preamble(venue_name: Optional[str], template_override: Optional[str] = None) -> Tuple[str, str]:
    """Get the LaTeX documentclass and packages for a venue.

    Args:
        venue_name: The target venue name (e.g. "NeurIPS 2026")
        template_override: Explicit template ID (e.g. "neurips"), overrides venue matching

    Returns:
        (documentclass_line, packages_block) tuple
    """
    template_id = template_override or _match_template(venue_name or "") or "arxiv"
    tmpl = KNOWN_TEMPLATES.get(template_id, KNOWN_TEMPLATES["arxiv"])

    return tmpl["documentclass"], tmpl["packages"]


def get_available_templates() -> List[Dict[str, str]]:
    """Return list of available template IDs with descriptions for the API."""
    result = []
    for tid, tmpl in KNOWN_TEMPLATES.items():
        result.append({
            "id": tid,
            "documentclass": tmpl["documentclass"],
            "has_download": len(tmpl["urls"]) > 0,
        })
    return result


def get_template_dir() -> str:
    """Return the template cache directory path."""
    TEMPLATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return str(TEMPLATE_CACHE_DIR)
