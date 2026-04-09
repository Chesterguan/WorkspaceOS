# Work Log: Progress Report Generator

**Date:** 2026-04-08
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

Software developers at research institutes need to regularly report progress to supervisors — weekly standups, monthly reports, quarterly reviews. Compiling these manually is tedious: gathering commit data, listing deliverables, tracking goals, formatting tables. ProjectScribe already has all the data; it just needs to assemble it into a clean, professional report.

## Solution

A **Work Log** page at `/worklog` that generates structured progress reports from real project data. Supports weekly, monthly, and quarterly cadences with goal tracking. Exports to DOCX (with tables, charts, and images) and PDF.

---

## Data Model

### New table: `work_logs`

```sql
CREATE TABLE work_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    period_type VARCHAR(20) NOT NULL,    -- "weekly" | "monthly" | "quarterly"
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    project_ids UUID[] NOT NULL,         -- which projects this covers
    content TEXT NOT NULL DEFAULT '',     -- generated markdown report
    goals JSONB,                         -- [{description, achieved, evidence}]
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_work_logs_period ON work_logs (period_start, period_end);
```

Migration 0013. Model: `backend/app/models/worklog.py`.

### Goals JSONB structure

```json
[
  {"description": "Ship JWT auth system", "achieved": true, "evidence": "18 tests passing, commit abc123"},
  {"description": "Publish HAVEN paper", "achieved": false, "evidence": "Draft complete, review pending"},
  {"description": "Expand test coverage to 30+", "achieved": true, "evidence": "35 tests now passing"}
]
```

---

## Report Templates

### Weekly (1 page, concise)

```markdown
## Weekly Report: Mar 31 - Apr 6, 2026

### Summary
2-3 sentences: focus area, key achievement, overall status.

### Goals Status
| Goal | Status | Evidence |
|------|--------|----------|
| Ship JWT auth | Done | 18 tests passing, dual auth working |
| Paper v2 pipeline | Done | E2E verified, roundtable review |

### Work Completed
- **ProjectScribe**: 40 commits — JWT auth, roundtable chat, file ingest
- **HAVEN**: 8 commits — literature review updates

### Key Metrics
| Metric | Count |
|--------|-------|
| Commits | 48 |
| Papers generated | 3 |
| Tests added | 17 |

### Next Week
- Priority 1: ...
- Priority 2: ...
```

### Monthly (2-3 pages, detailed)

Includes everything from weekly PLUS:
- Activity trend chart (4 weekly bars)
- Per-project breakdown table (project, commits, papers, drafts, status)
- Milestones achieved (with dates)
- Challenges encountered and how they were resolved
- Time allocation by project (pie-chart style breakdown)

### Quarterly (3-5 pages, strategic)

Includes everything from monthly PLUS:
- Cumulative metrics (total commits, papers, etc. for the quarter)
- Goal completion rate (X of Y goals achieved)
- Quarter-over-quarter comparison
- Strategic reflection: what worked, what didn't, what to change
- Next quarter objectives

---

## Architecture

### Backend

**New service: `backend/app/services/worklog_service.py`**

Functions:
- `gather_period_data(project_ids, start_date, end_date, db)` — queries commits, papers, drafts, syncs, memory for the given projects and date range. Returns structured data dict.
- `generate_report(period_type, period_data, goals, db)` — calls cloud AI with the right template (weekly/monthly/quarterly) and the gathered data. Returns markdown string.
- `export_to_docx(content, period_data, charts)` — converts markdown report to DOCX with python-docx: headings, tables, embedded chart images. Returns bytes.

**Data gathering queries:**
```python
# Commits in period
SELECT date_trunc('week', committed_at)::date, COUNT(*)
FROM github_commits
WHERE project_id IN (...) AND committed_at BETWEEN start AND end
GROUP BY 1

# Papers (blog_posts with paper tag) in period
SELECT title, created_at FROM blog_posts
WHERE project_id IN (...) AND tags @> ARRAY['paper'] AND created_at BETWEEN start AND end

# Drafts in period
SELECT platform, status, COUNT(*) FROM drafts
WHERE project_id IN (...) AND created_at BETWEEN start AND end
GROUP BY platform, status

# Sync activity
SELECT project_id, COUNT(*), SUM(commits_fetched) FROM sync_runs
WHERE project_id IN (...) AND completed_at BETWEEN start AND end AND status='completed'
GROUP BY project_id
```

**AI prompt template (weekly):**
```
You are generating a weekly progress report for a software developer at a research institute.
The audience is a research supervisor who values: clear deliverables, technical progress, 
research output, and evidence of impact.

Tone: professional but human-readable. Not corporate jargon. Show what was done and why it matters.

Given data:
{period_data as structured context}

Goals:
{goals list with achieved/not status}

Generate a weekly report in markdown with sections:
## Summary, ## Goals Status (table), ## Work Completed (by project), ## Key Metrics (table), ## Next Week
```

**New router: `backend/app/routers/worklog.py`**

Endpoints:
- `POST /worklog/generate` — generate a new report (period_type, start, end, project_ids, goals)
- `GET /worklog` — list saved reports (paginated, newest first)
- `GET /worklog/{id}` — get a specific report
- `PUT /worklog/{id}` — update a saved report (edit content, update goals)
- `DELETE /worklog/{id}` — delete a report
- `POST /worklog/{id}/export-docx` — export to DOCX (returns base64-encoded file)
- `POST /worklog/{id}/export-pdf` — export to PDF (reuses existing LaTeX pipeline)

**New schemas: `backend/app/schemas/worklog.py`**

```python
class WorkLogGoal(BaseModel):
    description: str
    achieved: bool = False
    evidence: str = ""

class GenerateWorkLogRequest(BaseModel):
    period_type: str  # "weekly" | "monthly" | "quarterly"
    period_start: str  # ISO date
    period_end: str
    project_ids: List[uuid.UUID]
    goals: List[WorkLogGoal] = []
    additional_instructions: Optional[str] = None

class WorkLogResponse(BaseModel):
    id: uuid.UUID
    title: str
    period_type: str
    period_start: str
    period_end: str
    project_ids: List[uuid.UUID]
    content: str
    goals: List[WorkLogGoal]
    created_at: datetime
    updated_at: datetime

class WorkLogListResponse(BaseModel):
    reports: List[WorkLogResponse]
    total: int

class ExportDocxResponse(BaseModel):
    docx_base64: str
    filename: str
```

### DOCX Export

Using `python-docx` library:

1. Parse markdown sections (split by `##` headers)
2. For each section:
   - Headings → `document.add_heading(text, level=N)`
   - Markdown tables → `document.add_table(rows, cols)` with styled cells
   - Bullet lists → `document.add_paragraph(text, style='List Bullet')`
   - Regular text → `document.add_paragraph(text)`
3. For charts (monthly/quarterly reports):
   - Generate activity chart as PNG using matplotlib (simple bar chart)
   - Embed with `document.add_picture(image_stream, width=Inches(5))`
4. Styling: professional, clean. Use default Word styles. Header with title + date range.

Dependencies: add `python-docx>=1.1.0` and `matplotlib>=3.9.0` to requirements.txt.

### Frontend

**New page: `frontend/app/worklog/page.tsx`**

Layout:
- Left panel (70%): report form + preview
- Right panel (30%): saved reports history

Form:
- Period type tabs: Weekly | Monthly | Quarterly
- Date range: auto-filled based on period type (this week, this month, this quarter) with manual override
- Project selector: checkboxes for all projects, "Select All" option
- Goals editor: add/remove goals, checkbox for achieved, text input for evidence
- "Generate Report" button
- Additional instructions textarea (optional)

Preview:
- Rendered markdown below the form
- Export buttons: DOCX, PDF, Copy Markdown

History sidebar:
- List of saved reports with: title, period type badge, date range, date created
- Click to load into preview

---

## Dependencies

New Python packages:
- `python-docx>=1.1.0` — DOCX generation with tables and images
- `matplotlib>=3.9.0` — chart rendering to PNG for DOCX embedding

---

## Scope Boundaries

### In scope
- Weekly, monthly, quarterly report templates
- Goal tracking (set, mark achieved, show evidence)
- Data gathering from commits, papers, drafts, syncs
- AI-generated report content
- DOCX export with tables + charts + images
- PDF export (reuse existing pipeline)
- Save/load report history
- Multi-project support

### Out of scope
- Email sending (export and attach manually)
- Calendar integration (no auto-scheduling of reports)
- Collaborative editing (single user)
- Slack/Teams posting
- Custom templates (3 built-in templates are sufficient)

---

## Success Criteria

- [ ] Generate a weekly report with real data from selected projects
- [ ] Goals table shows achieved vs pending with evidence
- [ ] Monthly report includes activity chart
- [ ] DOCX export produces a clean Word document with tables and embedded charts
- [ ] PDF export works
- [ ] Saved reports are loadable from history
- [ ] Works for single project or multiple projects
