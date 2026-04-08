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
    content: Optional[str] = None  # full paper body at this version (for diff view)


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


class ExportPdfRequest(BaseModel):
    blog_post_id: str
    template: str = Field(
        default="arxiv",
        description="LaTeX template to use",
    )


class ExportPdfResponse(BaseModel):
    pdf_base64: str  # base64-encoded PDF content
    filename: str
    page_count: Optional[int] = None


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


# ---------------------------------------------------------------------------
# V2 Pipeline schemas
# ---------------------------------------------------------------------------

class AgentLogEntry(BaseModel):
    agent: str          # "gemini_planner" | "gemini_writer" | "openai_critic" | ...
    action: str         # "plan" | "draft" | "review" | "revise" | "backtrack" | "coherence"
    section: Optional[str] = None  # "3. Methodology" or null for full-paper actions
    detail: str         # Human-readable summary
    score: Optional[int] = None  # Critic score if applicable
    timestamp: str      # ISO timestamp


class VenueGuidelinesSchema(BaseModel):
    venue_name: str
    page_limit: Optional[int] = None
    word_limit: Optional[int] = None
    template: Optional[str] = None
    anonymization: bool = False
    deadline: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    source: str = "manual"
    venue_url: Optional[str] = None


class ReviewerFeedback(BaseModel):
    reviewer_id: str
    reviewer_name: str
    modeled_after: str
    focus: str
    avatar: str = ""
    color: str = ""
    score: int
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    critical_issues: List[str] = Field(default_factory=list)


class PaperGenerateV2Response(BaseModel):
    blog_post_id: str
    title: str
    final_content: str
    bibtex: str
    latex: Optional[str] = None
    versions: List[PaperVersionSummary]
    review_summary: str
    agent_log: List[AgentLogEntry]
    venue_guidelines: Optional[VenueGuidelinesSchema] = None
    roundtable_reviews: Optional[List[ReviewerFeedback]] = None


class PaperEditRequest(BaseModel):
    instruction: str = Field(..., min_length=3, max_length=2000)
    target_section: Optional[str] = Field(
        default=None,
        description="Section to edit (e.g. '3. Methodology'), or null for whole paper",
    )
    target_pages: Optional[int] = Field(
        default=None,
        description="Target page count for condense operations",
    )
    target_venue: Optional[str] = Field(
        default=None,
        description="Venue name — triggers venue resolution for constraints",
    )


class PaperEditResponse(BaseModel):
    blog_post_id: str
    updated_content: str
    previous_version: int
    new_version: int
    changes_summary: str
    agent_log: List[AgentLogEntry]
    sections_modified: List[str]
