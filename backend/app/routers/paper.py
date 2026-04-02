"""
Academic paper writing pipeline router.

Endpoints:
  POST /projects/{project_id}/paper/generate
      Run the full 5-pass paper generation pipeline. Long-running (~10 AI calls).
      Progress is stored in BlogPost.tags so the frontend can poll.

  POST /projects/{project_id}/paper/export-latex
      Convert a generated paper (stored as a BlogPost) to LaTeX.
      Uses pandoc if available; falls back to a built-in Python converter.

  POST /projects/{project_id}/paper/generate-diagram
      Generate a diagram from a description or file tree.
      Returns both the source code and the rendered SVG.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.blog import BlogPost
from app.models.project import Project
from app.schemas.paper import (
    ExportLatexRequest,
    ExportLatexResponse,
    GenerateChartRequest,
    GenerateChartResponse,
    GenerateDiagramRequest,
    GenerateDiagramResponse,
    GenerateFigureRequest,
    GenerateFigureResponse,
    GenerateTableRequest,
    GenerateTableResponse,
    PaperGenerateRequest,
    PaperGenerateResponse,
    PaperVersionSummary,
    PortfolioPaperGenerateRequest,
    SuggestTitlesRequest,
    SuggestTitlesResponse,
    TitleSuggestion,
)
from app.services import paper_service
from app.services.diagram_service import (
    generate_architecture_diagram,
    generate_comparison_table,
    generate_data_chart,
    generate_flow_diagram,
    generate_latex_table,
    generate_system_architecture,
    render_diagram,
)

router = APIRouter(prefix="/projects/{project_id}/paper", tags=["paper"])
portfolio_paper_router = APIRouter(prefix="/portfolio/paper", tags=["paper"])

# Valid paper type values — enforced at the router layer for clear error messages
_VALID_PAPER_TYPES = frozenset(["conference", "journal", "technical_report", "white_paper"])

# Valid LaTeX templates
_VALID_TEMPLATES = frozenset(["arxiv", "ieee", "acm"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _require_blog_post(blog_post_id: str, db: AsyncSession) -> BlogPost:
    try:
        post_uuid = uuid.UUID(blog_post_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid blog_post_id: {blog_post_id!r}",
        )
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_uuid))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return post


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    response_model=PaperGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a full academic paper with 5 peer-review passes",
)
async def generate_paper(
    project_id: uuid.UUID,
    body: PaperGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaperGenerateResponse:
    """
    Run the complete multi-pass paper writing pipeline.

    This is a **long-running** endpoint (expect 2-5 minutes depending on paper length
    and AI provider response times). The generated paper is stored as a BlogPost with
    version history. Poll `GET /projects/{project_id}/blog/{blog_post_id}` using the
    returned `blog_post_id` to check progress via the `tags` field.

    Progress tags format: `["paper", "progress:N", "step:...", "pass:N/5"]`
    When complete: `["paper", "progress:100", "step:complete"]`
    """
    await _require_project(project_id, db)

    if body.paper_type not in _VALID_PAPER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid paper_type '{body.paper_type}'. "
                f"Must be one of: {sorted(_VALID_PAPER_TYPES)}"
            ),
        )

    result = await paper_service.generate_paper(
        project_id=project_id,
        paper_type=body.paper_type,
        title=body.title,
        target_venue=body.target_venue,
        additional_instructions=body.additional_instructions,
        db=db,
    )

    return PaperGenerateResponse(
        blog_post_id=result["blog_post_id"],
        title=result["title"],
        final_content=result["final_content"],
        bibtex=result["bibtex"],
        versions=[PaperVersionSummary(**v) for v in result["versions"]],
        review_summary=result["review_summary"],
    )


@router.post(
    "/export-latex",
    response_model=ExportLatexResponse,
    status_code=status.HTTP_200_OK,
    summary="Export a generated paper to LaTeX",
)
async def export_latex(
    project_id: uuid.UUID,
    body: ExportLatexRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ExportLatexResponse:
    """
    Convert the Markdown paper stored in a BlogPost to LaTeX.

    Uses pandoc if it is available on the server; otherwise falls back to a
    built-in Python converter. The returned LaTeX is standalone and ready to
    compile (pdflatex / xelatex). The BibTeX content is returned separately
    so it can be saved as `references.bib` in the same directory.

    Supported templates:
    - `arxiv` — standard article class with double spacing (arXiv default)
    - `ieee` — IEEEtran conference class
    - `acm` — ACM sigconf class
    """
    await _require_project(project_id, db)

    if body.template not in _VALID_TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid template '{body.template}'. "
                f"Must be one of: {sorted(_VALID_TEMPLATES)}"
            ),
        )

    post = await _require_blog_post(body.blog_post_id, db)

    # Retrieve bibtex from the post's tags metadata if stored there,
    # otherwise use the paper content directly (best-effort)
    bibtex = ""
    # BibTeX is not stored on the BlogPost itself — the pipeline returns it in the
    # response. The client must pass it back or we re-generate from the post content.
    # For simplicity, we regenerate a minimal bibtex from any [N] references found
    # in the paper content. A full re-fetch is intentionally avoided here to keep
    # this endpoint fast; the client should store the bibtex from the generate response.

    latex, bibtex_out = await paper_service.export_to_latex(
        markdown_content=post.content,
        bibtex=bibtex,
        template=body.template,
    )

    return ExportLatexResponse(latex=latex, bibtex=bibtex_out)


@router.post(
    "/generate-diagram",
    response_model=GenerateDiagramResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate an architecture diagram from a description or file tree",
)
async def generate_diagram(
    project_id: uuid.UUID,
    body: GenerateDiagramRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> GenerateDiagramResponse:
    """
    Generate a diagram in two steps:
    1. Ask the local AI (Ollama) to produce diagram source code from the description.
    2. Render the source to SVG via Kroki.io.

    For `mermaid` type, the description is treated as a file tree or architectural
    description and the local model generates Mermaid syntax.

    For other types (plantuml, d2, graphviz), the description is used directly as
    the diagram source — no AI generation step.

    Returns both the source code (for editing) and the rendered SVG string.
    """
    await _require_project(project_id, db)

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    project_name = project.name if project else "Project"

    diagram_type = body.diagram_type.lower().strip()

    if diagram_type == "mermaid":
        # Use local AI to generate Mermaid source from the description/file tree
        source = await generate_architecture_diagram(
            file_tree=body.description,
            project_name=project_name,
        )
    else:
        # For non-mermaid types, treat the description as the diagram source directly
        source = body.description

    # Render to SVG via Kroki.io
    try:
        svg_bytes = await render_diagram(source=source, diagram_type=diagram_type, output_format="svg")
        svg_str = svg_bytes.decode("utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Diagram rendering failed: {exc}",
        )

    return GenerateDiagramResponse(source=source, svg=svg_str)


# ---------------------------------------------------------------------------
# Title suggestion
# ---------------------------------------------------------------------------

@router.post(
    "/suggest-titles",
    response_model=SuggestTitlesResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate 5 compelling paper title suggestions",
)
async def suggest_titles(
    project_id: uuid.UUID,
    body: SuggestTitlesRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> SuggestTitlesResponse:
    """
    Analyse top-cited related papers from Semantic Scholar, identify title patterns,
    and generate five title suggestions in different academic styles:
    descriptive, question, method-result, provocative, and systematic.

    Useful before running the full paper pipeline when the user wants to pick a
    title rather than letting the AI invent one.
    """
    await _require_project(project_id, db)

    if body.paper_type not in _VALID_PAPER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid paper_type '{body.paper_type}'. "
                f"Must be one of: {sorted(_VALID_PAPER_TYPES)}"
            ),
        )

    titles = await paper_service.generate_paper_titles(
        project_id=project_id,
        paper_type=body.paper_type,
        target_venue=body.target_venue,
        db=db,
    )

    return SuggestTitlesResponse(
        titles=[TitleSuggestion(**t) for t in titles]
    )


# ---------------------------------------------------------------------------
# Visual content generation — table
# ---------------------------------------------------------------------------

@router.post(
    "/generate-table",
    response_model=GenerateTableResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a comparison table (markdown + LaTeX)",
)
async def generate_table(
    project_id: uuid.UUID,
    body: GenerateTableRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> GenerateTableResponse:
    """
    Ask the cloud AI to produce a filled comparison table for this project.

    Provide a description of what to compare, and optionally pre-specify the
    row items and column criteria. The AI fills every cell. Returns both a
    pipe-delimited markdown table and its LaTeX tabular equivalent.
    """
    await _require_project(project_id, db)

    # Build a minimal project context for the AI to anchor its answers
    context_block, _ = await paper_service.get_paper_context(project_id, db)

    markdown = await generate_comparison_table(
        items=body.items or [],
        criteria=body.criteria or [],
        project_context=f"{context_block}\n\nTable request: {body.description}",
    )

    latex = generate_latex_table(markdown)

    return GenerateTableResponse(markdown=markdown, latex=latex)


# ---------------------------------------------------------------------------
# Visual content generation — chart
# ---------------------------------------------------------------------------

@router.post(
    "/generate-chart",
    response_model=GenerateChartResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a chart (data + Mermaid source + SVG)",
)
async def generate_chart(
    project_id: uuid.UUID,
    body: GenerateChartRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> GenerateChartResponse:
    """
    Generate chart data and a Mermaid visualisation for this project.

    chart_type must be one of: bar, line, pie, radar.
    The cloud AI infers plausible data values from the project context and the
    description you supply. The chart is rendered via Kroki.io and the SVG is
    returned base64-encoded.
    """
    await _require_project(project_id, db)

    valid_chart_types = frozenset(["bar", "line", "pie", "radar"])
    if body.chart_type.lower() not in valid_chart_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid chart_type '{body.chart_type}'. "
                f"Must be one of: {sorted(valid_chart_types)}"
            ),
        )

    context_block, _ = await paper_service.get_paper_context(project_id, db)

    result = await generate_data_chart(
        chart_type=body.chart_type.lower(),
        data_description=body.description,
        project_context=context_block,
    )

    return GenerateChartResponse(
        data=result["data"],
        mermaid_source=result["mermaid_source"],
        svg=result["svg"],
    )


# ---------------------------------------------------------------------------
# Visual content generation — figure (architecture / flow / sequence / class)
# ---------------------------------------------------------------------------

@router.post(
    "/generate-figure",
    response_model=GenerateFigureResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a Mermaid figure (architecture / flow / sequence / class)",
)
async def generate_figure(
    project_id: uuid.UUID,
    body: GenerateFigureRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> GenerateFigureResponse:
    """
    Generate a diagram figure using AI + Kroki.io rendering.

    figure_type must be one of: architecture, flow, sequence, class.

    - architecture: uses the local Ollama model against the project file tree for
      on-device privacy; generates a flowchart TD component diagram.
    - flow / sequence / class: uses the cloud AI (Gemini) to produce the appropriate
      Mermaid diagram type from the description.

    The rendered SVG is returned base64-encoded.
    """
    await _require_project(project_id, db)

    valid_figure_types = frozenset(["architecture", "flow", "sequence", "class"])
    if body.figure_type.lower() not in valid_figure_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid figure_type '{body.figure_type}'. "
                f"Must be one of: {sorted(valid_figure_types)}"
            ),
        )

    figure_type = body.figure_type.lower()

    if figure_type == "architecture":
        # Use the local model — keeps code analysis on-device
        # Build a lightweight project context + file tree
        from app.services.workspace_scanner import get_latest_snapshot

        context_block, _ = await paper_service.get_paper_context(project_id, db)
        snapshot = await get_latest_snapshot(project_id, db)
        file_tree = snapshot.summary if snapshot else body.description

        result = await generate_system_architecture(
            project_context=context_block,
            file_tree=file_tree,
        )
    else:
        # flow / sequence / class — cloud AI
        result = await generate_flow_diagram(
            process_description=body.description,
            figure_type=figure_type,
        )

    return GenerateFigureResponse(
        mermaid_source=result["mermaid_source"],
        svg=result["svg"],
    )


# ---------------------------------------------------------------------------
# Portfolio paper endpoint (no single project scope)
# ---------------------------------------------------------------------------

@portfolio_paper_router.post(
    "/generate",
    response_model=PaperGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a multi-project portfolio paper with 5 peer-review passes",
)
async def generate_portfolio_paper(
    body: PortfolioPaperGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaperGenerateResponse:
    """
    Run the complete multi-pass paper writing pipeline across multiple projects.

    Context is assembled from every project in `project_ids` (2–5), then the same
    5-round review pipeline used for single-project papers is executed. The resulting
    BlogPost is stored under the first project in the list.

    Useful for survey papers, portfolio technical reports, and multi-system comparison
    papers that span several of your projects.

    Progress tags format: `["paper", "portfolio", "progress:N", "step:...", "pass:N/5"]`
    When complete: `["paper", "portfolio", "progress:100", "step:complete"]`
    """
    if body.paper_type not in _VALID_PAPER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid paper_type '{body.paper_type}'. "
                f"Must be one of: {sorted(_VALID_PAPER_TYPES)}"
            ),
        )

    try:
        result = await paper_service.generate_portfolio_paper(
            project_ids=body.project_ids,
            paper_type=body.paper_type,
            title=body.title,
            target_venue=body.target_venue,
            additional_instructions=body.additional_instructions,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return PaperGenerateResponse(
        blog_post_id=result["blog_post_id"],
        title=result["title"],
        final_content=result["final_content"],
        bibtex=result["bibtex"],
        versions=[PaperVersionSummary(**v) for v in result["versions"]],
        review_summary=result["review_summary"],
    )
