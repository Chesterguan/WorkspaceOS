"""
Diagram generation service using Kroki.io (free, no auth required).

Kroki.io supports Mermaid, PlantUML, D2, Graphviz, and many others through a
single unified API. We POST the diagram source text and receive back the
rendered image (SVG or PNG).

For architecture diagrams from file trees, we ask the local Ollama model to
generate Mermaid source — keeping the AI inference on-device.
"""
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Kroki.io public instance — free for open usage
_KROKI_BASE = "https://kroki.io"

# Supported diagram types by Kroki — subset we expose
SUPPORTED_DIAGRAM_TYPES = frozenset(
    ["mermaid", "plantuml", "d2", "graphviz", "ditaa", "c4plantuml"]
)


async def render_diagram(
    source: str,
    diagram_type: str = "mermaid",
    output_format: str = "svg",
) -> bytes:
    """
    POST diagram source to Kroki.io and return the rendered image bytes.

    Args:
        source: The diagram source text (e.g. Mermaid markdown, PlantUML, D2).
        diagram_type: One of the SUPPORTED_DIAGRAM_TYPES (default: "mermaid").
        output_format: "svg" or "png" (default: "svg").

    Returns:
        Raw bytes of the rendered image. Raises httpx.HTTPStatusError on failure.
    """
    if diagram_type not in SUPPORTED_DIAGRAM_TYPES:
        raise ValueError(
            f"Unsupported diagram type '{diagram_type}'. "
            f"Supported: {sorted(SUPPORTED_DIAGRAM_TYPES)}"
        )

    url = f"{_KROKI_BASE}/{diagram_type}/{output_format}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                content=source.encode("utf-8"),
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "Accept": "image/svg+xml" if output_format == "svg" else "image/png",
                },
            )
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Kroki.io render failed: HTTP %s for %s/%s",
            exc.response.status_code,
            diagram_type,
            output_format,
        )
        raise
    except Exception:
        logger.exception("render_diagram failed for type=%s format=%s", diagram_type, output_format)
        raise


async def generate_architecture_diagram(file_tree: str, project_name: str) -> str:
    """
    Ask the local Ollama model to produce Mermaid architecture diagram source
    from a project file tree.

    The returned string is raw Mermaid source code (not rendered). Pass it to
    render_diagram() to get the SVG.

    Args:
        file_tree: A text representation of the project directory structure.
        project_name: The project name for diagram labelling.

    Returns:
        Mermaid diagram source string. Returns a minimal fallback diagram on
        failure so callers always get something renderable.
    """
    from app.services.ai_client import get_local_client

    system = (
        "You are an expert software architect. Given a project file tree, you produce "
        "a clear Mermaid architecture diagram showing the high-level components and their "
        "relationships. Output ONLY valid Mermaid source code — no explanation, no markdown "
        "code fences, no comments outside the diagram. Start directly with 'graph TD' or "
        "'flowchart TD'. Use concise node labels (max 4 words each)."
    )
    user = (
        f"Project: {project_name}\n\n"
        f"File tree:\n{file_tree}\n\n"
        "Produce a Mermaid architecture diagram (flowchart TD) showing the main components "
        "inferred from this file structure and their relationships. "
        "Output ONLY the Mermaid source, starting with 'flowchart TD'."
    )

    try:
        ai = get_local_client()
        raw = await ai.complete(system=system, user=user)
        # Strip any accidental code fences the model may have added
        mermaid_src = _strip_code_fences(raw).strip()
        if not mermaid_src or not mermaid_src.startswith(("graph", "flowchart", "sequenceDiagram")):
            logger.warning(
                "generate_architecture_diagram: model output did not start with valid Mermaid; "
                "returning fallback. Raw (first 200 chars): %s",
                raw[:200],
            )
            return _fallback_diagram(project_name)
        return mermaid_src
    except Exception:
        logger.exception(
            "generate_architecture_diagram failed for project: %s", project_name
        )
        return _fallback_diagram(project_name)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    """Remove ```mermaid ... ``` or ``` ... ``` wrappers if the model added them."""
    # Match optional language tag after opening fence
    pattern = r"```(?:mermaid|plantuml|d2)?\s*\n?(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    return text


def _fallback_diagram(project_name: str) -> str:
    """Return a minimal valid Mermaid diagram as a safe fallback."""
    safe_name = re.sub(r"[^A-Za-z0-9 ]", "", project_name)[:30]
    return (
        f'flowchart TD\n'
        f'    A["{safe_name}"] --> B["Backend API"]\n'
        f'    A --> C["Frontend"]\n'
        f'    B --> D["Database"]\n'
    )
