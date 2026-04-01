"""
Pydantic schemas for the academic paper writing pipeline.
"""
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PaperGenerateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    paper_type: str = Field(
        default="conference",
        description="One of: conference, journal, technical_report, white_paper",
    )
    target_venue: Optional[str] = Field(
        default=None,
        description="e.g. 'AAAI 2026', 'Nature Digital Medicine', 'IEEE TNNLS'",
    )
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Free-text instructions to the writer (focus areas, excluded sections, etc.)",
    )


class PaperVersionSummary(BaseModel):
    """Metadata for one review-revision cycle stored as a BlogPostVersion."""
    version: int
    review_name: str
    score: int  # 1-10 from the reviewer
    review_notes: str
    diff_stats: Dict  # {lines_added, lines_removed, lines_changed, similarity_pct}


class PaperGenerateResponse(BaseModel):
    blog_post_id: str  # UUID of the BlogPost storing the paper
    title: str
    final_content: str  # Markdown — the fully revised paper
    bibtex: str  # combined .bib content for all cited papers
    versions: List[PaperVersionSummary]
    review_summary: str  # human-readable summary of all review passes


class ExportLatexRequest(BaseModel):
    blog_post_id: str
    template: str = Field(
        default="arxiv",
        description="LaTeX template: 'arxiv', 'ieee', or 'acm'",
    )


class ExportLatexResponse(BaseModel):
    latex: str
    bibtex: str


class PortfolioPaperGenerateRequest(BaseModel):
    project_ids: List[uuid.UUID] = Field(..., min_length=2, max_length=5)
    title: str = Field(..., min_length=3, max_length=500)
    paper_type: str = Field(
        default="technical_report",
        description="One of: conference, journal, technical_report, white_paper",
    )
    target_venue: Optional[str] = Field(
        default=None,
        description="e.g. 'AAAI 2026', 'Nature Digital Medicine', 'IEEE TNNLS'",
    )
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Free-text instructions to the writer (focus areas, excluded sections, etc.)",
    )


class GenerateDiagramRequest(BaseModel):
    description: str = Field(
        ...,
        description="Natural language description or file tree to generate a diagram from",
    )
    diagram_type: str = Field(
        default="mermaid",
        description="Diagram language: mermaid, plantuml, d2, graphviz",
    )


class GenerateDiagramResponse(BaseModel):
    source: str  # the diagram source code (Mermaid / PlantUML / etc.)
    svg: str     # rendered SVG as a UTF-8 string
