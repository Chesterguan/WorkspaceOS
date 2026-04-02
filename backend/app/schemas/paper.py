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
    changes_made: str = ""  # human-readable summary of the diff
    diff_stats: Dict  # {lines_added, lines_removed, lines_changed, similarity_pct}


class PaperGenerateResponse(BaseModel):
    blog_post_id: str  # UUID of the BlogPost storing the paper
    title: str
    final_content: str  # Markdown — the fully revised paper
    bibtex: str  # combined .bib content for all cited papers
    versions: List[PaperVersionSummary]
    review_summary: str  # human-readable summary of all review passes
    latex: Optional[str] = None  # LaTeX source generated inline after the pipeline


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


# ---------------------------------------------------------------------------
# Title suggestion schemas
# ---------------------------------------------------------------------------

class SuggestTitlesRequest(BaseModel):
    paper_type: str = Field(
        default="conference",
        description="One of: conference, journal, technical_report, white_paper",
    )
    target_venue: Optional[str] = Field(
        default=None,
        description="e.g. 'AAAI 2026', 'Nature Digital Medicine'",
    )


class TitleSuggestion(BaseModel):
    title: str
    style: str        # descriptive | question | method-result | provocative | systematic
    rationale: str    # one-sentence explanation of why this title works


class SuggestTitlesResponse(BaseModel):
    titles: List[TitleSuggestion]


# ---------------------------------------------------------------------------
# Visual content generation schemas
# ---------------------------------------------------------------------------

class GenerateTableRequest(BaseModel):
    description: str = Field(
        ...,
        description="What should the table compare / show?",
    )
    items: Optional[List[str]] = Field(
        default=None,
        description="Row items to compare (AI fills if omitted)",
    )
    criteria: Optional[List[str]] = Field(
        default=None,
        description="Column criteria/dimensions (AI fills if omitted)",
    )


class GenerateTableResponse(BaseModel):
    markdown: str   # pipe-delimited markdown table
    latex: str      # LaTeX tabular equivalent


class GenerateChartRequest(BaseModel):
    chart_type: str = Field(
        ...,
        description="One of: bar, line, pie, radar",
    )
    description: str = Field(
        ...,
        description="What data should the chart visualise?",
    )


class GenerateChartResponse(BaseModel):
    data: Dict           # structured data dict (labels + values)
    mermaid_source: str  # Mermaid pie/xychart source
    svg: str             # base64-encoded rendered SVG


class GenerateFigureRequest(BaseModel):
    figure_type: str = Field(
        ...,
        description="One of: architecture, flow, sequence, class",
    )
    description: str = Field(
        ...,
        description="Natural-language description of the diagram",
    )


class GenerateFigureResponse(BaseModel):
    mermaid_source: str  # generated Mermaid source
    svg: str             # base64-encoded rendered SVG
