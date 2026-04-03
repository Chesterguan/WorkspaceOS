"""
Diagram generation service using Kroki.io (free, no auth required).

Visual content generation — charts, tables, and architecture diagrams:
- generate_comparison_table : AI-filled markdown comparison table
- generate_data_chart       : Chart data + Mermaid/SVG visualisation
- generate_system_architecture: Architecture diagram from file tree
- generate_flow_diagram     : Process/workflow Mermaid diagram
- generate_latex_table      : Markdown → LaTeX tabular conversion

Kroki.io supports Mermaid, PlantUML, D2, Graphviz, and many others through a
single unified API. We POST the diagram source text and receive back the
rendered image (SVG or PNG).

For architecture diagrams from file trees, we ask the local Ollama model to
generate Mermaid source — keeping the AI inference on-device.
"""
import base64
import json as _json
import logging
import re
from typing import Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Helpers shared by the new visual generation functions
# ---------------------------------------------------------------------------

def _svg_to_base64(svg_bytes: bytes) -> str:
    """Base64-encode SVG bytes for safe transport in JSON responses."""
    return base64.b64encode(svg_bytes).decode("utf-8")


async def _render_mermaid_b64(mermaid_src: str) -> str:
    """Render Mermaid source via Kroki and return base64-encoded SVG string.

    Returns an empty string on failure so callers can degrade gracefully.
    """
    try:
        svg_bytes = await render_diagram(mermaid_src, diagram_type="mermaid", output_format="svg")
        return _svg_to_base64(svg_bytes)
    except Exception:
        logger.exception("_render_mermaid_b64 failed for source (first 100): %s", mermaid_src[:100])
        return ""


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

async def generate_comparison_table(
    items: List[str],
    criteria: List[str],
    project_context: str,
) -> str:
    """
    Generate a markdown comparison table using cloud AI.

    The AI fills each cell based on project context and its literature knowledge.
    If items or criteria are empty the AI infers suitable ones from context.

    Returns a pipe-delimited markdown table string.
    """
    from app.services.ai_client import get_cloud_client

    ai = get_cloud_client()

    items_hint = (
        f"Rows (items to compare): {', '.join(items)}"
        if items
        else "Infer 4–6 relevant items to compare from the project context."
    )
    criteria_hint = (
        f"Columns (comparison criteria): {', '.join(criteria)}"
        if criteria
        else "Infer 4–6 meaningful evaluation criteria from the project context."
    )

    system = (
        "You are an expert at creating clear, accurate academic comparison tables. "
        "You fill each table cell with a concise, factually accurate value (yes/no, "
        "brief phrase, or short rating). Never leave cells empty."
    )
    user = (
        f"## Project Context\n{project_context}\n\n"
        f"## Table Specification\n{items_hint}\n{criteria_hint}\n\n"
        "Generate a complete markdown comparison table. "
        "Use | as cell delimiter and include a separator row (|---|---|...) after the header. "
        "Output ONLY the table — no explanatory text before or after."
    )

    try:
        raw = await ai.complete(system=system, user=user)
        # Extract the table block (first contiguous block of lines starting with |)
        table_lines: List[str] = []
        in_table = False
        for line in raw.splitlines():
            if line.strip().startswith("|"):
                table_lines.append(line)
                in_table = True
            elif in_table:
                # Stop at the first non-table line after the table started
                break
        if table_lines:
            return "\n".join(table_lines)
        # Fallback: return the whole raw response trimmed
        return raw.strip()
    except Exception:
        logger.exception("generate_comparison_table: AI call failed")
        return "| Item | Criteria |\n|------|----------|\n| (generation failed) | — |"


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

# Mermaid chart types supported natively by Kroki
_CHART_TYPE_MAP: Dict[str, str] = {
    "pie": "pie",
    "bar": "xychart-beta",
    "line": "xychart-beta",
    "radar": "pie",  # Mermaid has no native radar; fall back to pie with note
}


async def generate_data_chart(
    chart_type: str,
    data_description: str,
    project_context: str,
) -> Dict:
    """
    Generate chart data plus a Mermaid visualisation rendered via Kroki.

    Steps:
    1. Cloud AI generates plausible data based on project context and description.
    2. The data is converted to the appropriate Mermaid chart syntax.
    3. Kroki renders the Mermaid source to SVG.

    Returns:
        {
            "data": dict of labels/values,
            "mermaid_source": str,
            "svg": base64-encoded SVG string,
        }
    """
    from app.services.ai_client import get_cloud_client

    ai = get_cloud_client()
    chart_type = chart_type.lower().strip()

    system = (
        "You are a data visualisation expert. Given a description of what a chart should show, "
        "you produce a JSON object with the chart data. "
        "Always output ONLY a JSON object with two keys: "
        '"labels" (list of strings) and "values" (list of numbers). '
        "No markdown fences, no extra text."
    )
    user = (
        f"## Project Context\n{project_context}\n\n"
        f"## Chart Request\nType: {chart_type}\n"
        f"Description: {data_description}\n\n"
        "Generate realistic data for this chart. Output ONLY the JSON object."
    )

    # Get data from AI
    data: Dict = {"labels": [], "values": []}
    mermaid_src = ""
    try:
        raw = await ai.complete(system=system, user=user)
        # Strip any accidental code fences
        raw = _strip_json_fences(raw)
        parsed = _json.loads(raw)
        labels: List = parsed.get("labels", [])
        values: List = parsed.get("values", [])
        data = {"labels": labels, "values": values}
    except Exception:
        logger.exception("generate_data_chart: AI/JSON parsing failed")
        labels, values = ["Item A", "Item B", "Item C"], [30, 50, 20]
        data = {"labels": labels, "values": values}

    # Build Mermaid source
    labels = data["labels"]
    values = data["values"]

    if chart_type == "pie":
        lines = ["pie title Chart"]
        for lbl, val in zip(labels, values):
            lines.append(f'    "{lbl}" : {val}')
        mermaid_src = "\n".join(lines)

    elif chart_type in ("bar", "line"):
        x_axis = ", ".join(f'"{lbl}"' for lbl in labels)
        val_list = ", ".join(str(v) for v in values)
        chart_keyword = "bar" if chart_type == "bar" else "line"
        mermaid_src = (
            "xychart-beta\n"
            f'    title "{data_description[:60]}"\n'
            f"    x-axis [{x_axis}]\n"
            f"    y-axis \"Value\"\n"
            f"    {chart_keyword} [{val_list}]"
        )

    elif chart_type == "radar":
        # Mermaid doesn't support radar natively — render as pie with a note
        lines = ['pie title Radar (rendered as pie — Mermaid limitation)']
        for lbl, val in zip(labels, values):
            lines.append(f'    "{lbl}" : {val}')
        mermaid_src = "\n".join(lines)

    else:
        # Unknown type — generic pie
        lines = ["pie title Chart"]
        for lbl, val in zip(labels, values):
            lines.append(f'    "{lbl}" : {val}')
        mermaid_src = "\n".join(lines)

    svg_b64 = await _render_mermaid_b64(mermaid_src)

    return {
        "data": data,
        "mermaid_source": mermaid_src,
        "svg": svg_b64,
    }


# ---------------------------------------------------------------------------
# System architecture diagram (cloud AI + Kroki)
# ---------------------------------------------------------------------------

async def generate_system_architecture(
    project_context: str,
    file_tree: str,
) -> Dict:
    """
    Generate a system architecture diagram from project structure using local AI.

    Steps:
    1. Local AI (Ollama) analyses file tree + context to identify components.
    2. Generates Mermaid flowchart source.
    3. Kroki renders to SVG.

    Returns:
        {
            "mermaid_source": str,
            "svg": base64-encoded SVG string,
        }
    """
    from app.services.ai_client import get_local_client

    system = (
        "You are an expert software architect. Given a project context and file tree, produce "
        "a clear Mermaid architecture diagram. "
        "Output ONLY valid Mermaid source code — no explanation, no markdown fences. "
        "Start directly with 'flowchart TD'. Use concise node labels (max 4 words each)."
    )
    user = (
        f"## Project Context\n{project_context}\n\n"
        f"## File Tree\n{file_tree}\n\n"
        "Produce a Mermaid flowchart TD showing the main components and their relationships."
    )

    ai = get_local_client()
    try:
        raw = await ai.complete(system=system, user=user)
        mermaid_src = _strip_code_fences(raw).strip()
        if not mermaid_src or not mermaid_src.startswith(("graph", "flowchart")):
            logger.warning(
                "generate_system_architecture: invalid output, using fallback. "
                "Raw (first 200 chars): %s",
                raw[:200],
            )
            mermaid_src = _fallback_diagram("Project")
    except Exception:
        logger.exception("generate_system_architecture: local AI call failed")
        mermaid_src = _fallback_diagram("Project")

    svg_b64 = await _render_mermaid_b64(mermaid_src)

    return {
        "mermaid_source": mermaid_src,
        "svg": svg_b64,
    }


# ---------------------------------------------------------------------------
# Flow / process diagram (cloud AI + Kroki)
# ---------------------------------------------------------------------------

async def generate_flow_diagram(
    process_description: str,
    figure_type: str = "flow",
) -> Dict:
    """
    Generate a process/workflow diagram from a natural-language description.

    figure_type controls the Mermaid diagram style:
    - "flow" / "architecture": flowchart TD
    - "sequence": sequenceDiagram
    - "class": classDiagram

    Returns:
        {
            "mermaid_source": str,
            "svg": base64-encoded SVG string,
        }
    """
    from app.services.ai_client import get_cloud_client

    ai = get_cloud_client()

    type_map: Dict[str, Tuple[str, str]] = {
        "flow":         ("flowchart TD",    "flowchart TD"),
        "architecture": ("flowchart TD",    "flowchart TD"),
        "sequence":     ("sequenceDiagram", "sequenceDiagram"),
        "class":        ("classDiagram",    "classDiagram"),
    }
    start_keyword, example_start = type_map.get(
        figure_type.lower(), ("flowchart TD", "flowchart TD")
    )

    system = (
        f"You are an expert diagram author. Produce a Mermaid {start_keyword} diagram. "
        "Output ONLY valid Mermaid source code — no explanation, no markdown fences, "
        f"no comments outside the diagram. Start directly with '{example_start}'."
    )
    user = (
        f"Description: {process_description}\n\n"
        f"Generate a Mermaid {start_keyword} diagram. "
        "Use clear, concise labels. Output ONLY the Mermaid source."
    )

    try:
        raw = await ai.complete(system=system, user=user)
        mermaid_src = _strip_code_fences(raw).strip()
        # Validate the output starts with a known Mermaid keyword
        valid_starts = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram")
        if not any(mermaid_src.startswith(s) for s in valid_starts):
            logger.warning(
                "generate_flow_diagram: invalid output, using fallback. "
                "Raw (first 200 chars): %s",
                raw[:200],
            )
            mermaid_src = (
                f"{example_start}\n"
                '    A["Start"] --> B["Process"]\n'
                '    B --> C["End"]'
            )
    except Exception:
        logger.exception("generate_flow_diagram: AI call failed")
        mermaid_src = (
            f"{example_start}\n"
            '    A["Start"] --> B["Process"]\n'
            '    B --> C["End"]'
        )

    svg_b64 = await _render_mermaid_b64(mermaid_src)

    return {
        "mermaid_source": mermaid_src,
        "svg": svg_b64,
    }


# ---------------------------------------------------------------------------
# LaTeX table conversion
# ---------------------------------------------------------------------------

def generate_latex_table(markdown_table: str) -> str:
    """
    Convert a pipe-delimited markdown table to a LaTeX tabular environment.

    Rules:
    - The first row becomes the header (\\hline after it).
    - The separator row (|---|...) is skipped.
    - Cells are joined with & and rows terminated with \\\\.
    - Special LaTeX characters in cell content are escaped.
    """
    lines = [l.strip() for l in markdown_table.strip().splitlines() if l.strip()]

    table_rows: List[List[str]] = []
    for line in lines:
        if not line.startswith("|"):
            continue
        # Skip separator rows (e.g. |---|---|)
        stripped = line.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")
        if not stripped:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        table_rows.append(cells)

    if not table_rows:
        return "% Could not parse markdown table\n"

    col_count = max(len(row) for row in table_rows)
    col_spec = " | ".join(["l"] * col_count)

    def _esc(text: str) -> str:
        return (
            text.replace("\\", "\\textbackslash{}")
                .replace("&", "\\&")
                .replace("%", "\\%")
                .replace("$", "\\$")
                .replace("#", "\\#")
                .replace("_", "\\_")
                .replace("{", "\\{")
                .replace("}", "\\}")
                .replace("~", "\\textasciitilde{}")
                .replace("^", "\\textasciicircum{}")
        )

    latex_lines: List[str] = [
        f"\\begin{{tabular}}{{|{col_spec}|}}",
        "\\hline",
    ]
    for row_idx, row in enumerate(table_rows):
        # Pad or truncate to col_count
        padded = row[:col_count] + [""] * (col_count - len(row))
        cell_str = " & ".join(_esc(c) for c in padded)
        latex_lines.append(f"    {cell_str} \\\\")
        if row_idx == 0:
            latex_lines.append("\\hline")

    latex_lines += ["\\hline", "\\end{tabular}"]
    return "\n".join(latex_lines)


# ---------------------------------------------------------------------------
# Private helpers (additional)
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if the AI added them."""
    pattern = r"```(?:json)?\s*\n?(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    return text
