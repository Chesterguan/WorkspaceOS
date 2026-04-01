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
    GenerateDiagramRequest,
    GenerateDiagramResponse,
    PaperGenerateRequest,
    PaperGenerateResponse,
    PaperVersionSummary,
    PortfolioPaperGenerateRequest,
)
from app.services import paper_service
from app.services.diagram_service import generate_architecture_diagram, render_diagram

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
