# Paper Roundtable Review: Multi-Perspective Academic Review Panel

**Date:** 2026-04-07
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

The paper pipeline v2 uses a single reviewer (openai_critic) for per-section review during drafting and a single coherence pass after assembly. While effective at catching per-section issues, this single-perspective review misses the diverse feedback a real peer review panel would provide — technical rigor, novelty assessment, writing quality, practical relevance, design elegance, and accessibility are all different dimensions that benefit from dedicated expert attention.

## Solution

Replace the Phase 3 coherence-only pass with a **roundtable review** — 6 named reviewers modeled after prominent academics, each with a unique reviewing philosophy and focus area. Reviewers critique the assembled paper in parallel, then the writer revises based on combined feedback.

---

## Reviewer Panel

6 reviewers, each with a unique system prompt encoding their real reviewing philosophy.

| ID | Modeled After | Focus Area | Key Questions |
|---|---|---|---|
| `technical_rigor` | Yoshua Bengio | Methodology, math, reproducibility | Are claims supported? Is the method rigorous? Can someone reproduce this? |
| `novelty_positioning` | Yann LeCun | Novelty, related work, positioning | What's actually new here? Is related work comprehensive and fair? |
| `writing_clarity` | Steven Pinker | Sentence clarity, structure, flow | Is each paragraph clear? Does the paper flow logically? Is jargon minimized? |
| `practical_impact` | Andrew Ng | Real-world applicability, scalability | Does this matter in practice? What are the honest limitations? |
| `design_elegance` | Saining Xie | Architecture, simplicity, ablations | Are design choices justified? Is this unnecessarily complex? Are ablations sufficient? |
| `science_communication` | Eric Topol | Accessibility, narrative, big-picture | Can a non-specialist follow this? Is the broader significance clear? |

### ReviewerConfig Data Structure

```python
@dataclass
class ReviewerConfig:
    id: str
    name: str
    modeled_after: str
    focus: str
    system_prompt: str
```

Stored in `backend/app/services/paper_reviewers.py` as `REVIEWER_REGISTRY: Dict[str, ReviewerConfig]`.

---

## Pipeline Integration

### Modified v2 Pipeline Flow

```
Phase 1: PLAN (unchanged)
  gemini_planner → outline + page budgets

Phase 2: DRAFT (unchanged)
  For each section: gemini_writer drafts → openai_critic reviews → revise if < 8

Phase 3: ROUNDTABLE REVIEW (replaces old merge+coherence)
  Step 1: gemini_editor assembles all sections + coherence pass (same as before)
  Step 2: 6 reviewers critique the assembled paper in parallel
  Step 3: gemini_writer receives combined feedback brief and revises
  Step 4: If any reviewer scored < 7, run one more round (max 2 rounds total)

Phase 4: FINALIZE (unchanged)
  BibTeX + LaTeX export
```

### Phase 3 Detail

**Step 1 — Assembly:** Same as the current `_phase_merge()` first half. The editor assembles sections and runs a coherence/transition pass.

**Step 2 — Parallel Review:** All 6 reviewers receive the same assembled paper. Each reviews from their specific angle. Each outputs:

```python
{
    "score": 8,          # 1-10 for their focus area
    "strengths": ["..."],
    "weaknesses": ["..."],
    "suggestions": ["..."],
    "critical_issues": ["..."]   # must-fix before publication
}
```

All 6 calls run via `asyncio.gather()` (same pattern as co-founder roundtable).

**Step 3 — Combined Revision:** The writer receives a structured revision brief:

```
## Roundtable Review Summary

### Technical Rigor (Yoshua Bengio) — 7/10
Strengths: [...]
Critical issues: [...]
Suggestions: [...]

### Novelty & Positioning (Yann LeCun) — 8/10
...

[all 6 reviewers]

### Priority Revision Guide
1. Critical issues (must fix): [deduplicated list]
2. Important suggestions: [deduplicated list]
3. Minor improvements: [deduplicated list]
```

The writer revises the entire paper addressing all critical issues and as many suggestions as feasible.

**Step 4 — Optional Second Round:** If any reviewer scored < 7 (indicating significant issues), run the panel again on the revised paper. Maximum 2 roundtable rounds to prevent infinite loops.

### Cost Analysis

Current v2 Phase 3: 2 AI calls (editor + critic)
New Phase 3: 1 editor + 6 reviewers + 1 writer revision = 8 calls (first round)
With optional second round: up to 15 calls

This is ~4x more than before, but Phase 3 only runs once after the full paper is assembled (not per-section), so the absolute cost is manageable (~$0.10-0.20 extra per paper at Gemini Flash / GPT-4o rates).

---

## Reviewer System Prompts

Each prompt is ~400-500 words encoding the reviewer's real philosophy. All share a common output format suffix.

### Common Output Suffix

```
OUTPUT FORMAT — respond with ONLY a JSON object:
{
    "score": <1-10>,
    "strengths": ["strength 1", "strength 2", ...],
    "weaknesses": ["weakness 1", "weakness 2", ...],
    "suggestions": ["suggestion 1", "suggestion 2", ...],
    "critical_issues": ["issue 1", ...]
}

Score strictly:
- 9-10: Publication-ready, exceptional work
- 7-8: Good, minor revisions needed
- 5-6: Major revisions required
- 1-4: Fundamental problems, not ready for review

Be specific: quote passages, reference section numbers, give concrete examples.
```

### Technical Rigor (Yoshua Bengio style)

Focus: mathematical correctness, experimental methodology, reproducibility, theoretical grounding. Asks "is this provably correct?" and "could someone reproduce this from the paper alone?"

### Novelty & Positioning (Yann LeCun style)

Focus: what's genuinely new vs incremental, related work completeness, honest comparison with prior art. Blunt about overclaiming. Asks "would this change how people think about the problem?"

### Writing Clarity (Steven Pinker style)

Focus: sentence-level clarity, paragraph structure, logical flow between sections, abstract self-containedness, jargon elimination. Rewrites unclear passages as examples.

### Practical Impact (Andrew Ng style)

Focus: real-world applicability, deployment considerations, scalability, honest limitations, who benefits. Asks "would a practitioner use this?" and "what's the path from paper to product?"

### Design Elegance (Saining Xie style)

Focus: architectural choices, simplicity vs complexity tradeoff, ablation study rigor, component necessity. Asks "is every component justified?" and "could this be simpler?"

### Science Communication (Eric Topol style)

Focus: accessibility to broader audience, narrative arc, translating technical jargon, significance framing. Asks "would a smart non-specialist understand the importance?" and "does the introduction motivate the work clearly?"

---

## Backend Changes

### New File: `backend/app/services/paper_reviewers.py`

Contains:
- `ReviewerConfig` dataclass
- `REVIEWER_REGISTRY` dict (6 entries with system prompts)
- `get_reviewer(id)` → ReviewerConfig
- `get_all_reviewers()` → List[ReviewerConfig]
- `run_review_roundtable(paper_content, venue, agent_log) → List[dict]` — dispatches 6 parallel reviews, returns structured results

### Modified: `backend/app/services/paper_pipeline_v2.py`

- `_phase_merge()` renamed/replaced with `_phase_roundtable_review()`
- New function calls `run_review_roundtable()` from paper_reviewers
- Builds combined revision brief from all 6 reviews
- Writer revises based on brief
- Optional second round if min score < 7
- Agent log captures each reviewer's feedback with name

### Modified: `backend/app/schemas/paper.py`

- Add `ReviewerFeedback` schema for the API response:
```python
class ReviewerFeedback(BaseModel):
    reviewer_id: str
    reviewer_name: str
    focus: str
    score: int
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    critical_issues: List[str]
```

- Add `roundtable_reviews: Optional[List[ReviewerFeedback]]` to `PaperGenerateV2Response`

### No Migration Needed

Reviewer feedback stored in the existing agent_log (returned in API response). The `roundtable_reviews` field gives structured access.

---

## Frontend Changes

### Modified: `frontend/app/projects/[projectId]/research/paper/page.tsx`

In the review timeline / agent log section, display roundtable reviews with reviewer badges (reuse the same pattern as co-founder advisor badges — colored left border, name, focus area).

### New Type: `frontend/lib/types.ts`

```typescript
export interface ReviewerFeedback {
    reviewer_id: string;
    reviewer_name: string;
    focus: string;
    score: number;
    strengths: string[];
    weaknesses: string[];
    suggestions: string[];
    critical_issues: string[];
}
```

Add `roundtable_reviews?: ReviewerFeedback[]` to `PaperGenerateV2Response`.

---

## Scope Boundaries

### In scope
- 6 named reviewers with unique system prompts
- Parallel dispatch after paper assembly (Phase 3)
- Combined revision brief for writer
- Optional second round for low scores
- Reviewer feedback in API response + agent log
- Frontend display of reviewer feedback

### Out of scope
- Per-section roundtable (too expensive, B approach chosen)
- Reviewer avatars (role badges with colored borders are sufficient)
- Reviewer selection/routing (all 6 always review — papers benefit from all angles)
- User-customizable reviewer panel

---

## Success Criteria

- [ ] 6 reviewers run in parallel after paper assembly
- [ ] Each reviewer produces structured feedback (score, strengths, weaknesses, suggestions, critical issues)
- [ ] Writer receives combined revision brief and revises
- [ ] Second round triggers if any score < 7
- [ ] Agent log shows all reviewer names and scores
- [ ] Frontend displays reviewer feedback with name badges
- [ ] Average review score improves vs single-critic baseline
