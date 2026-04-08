# Paper Roundtable Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-critic Phase 3 in the paper pipeline v2 with a 6-reviewer roundtable panel that critiques in parallel from different academic perspectives (technical rigor, novelty, writing, impact, design, communication).

**Architecture:** New `paper_reviewers.py` module defines 6 reviewer configs with system prompts. The `_phase_merge()` in `paper_pipeline_v2.py` is replaced with `_phase_roundtable_review()` that assembles sections, runs coherence pass, dispatches 6 parallel reviews, builds a combined revision brief, and has the writer revise. Optional second round if any score < 7.

**Tech Stack:** Python 3.9+ (asyncio.gather for parallel dispatch), Gemini Flash / GPT-4o, Next.js 16

**Spec:** `docs/superpowers/specs/2026-04-07-paper-roundtable-review-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `backend/app/services/paper_reviewers.py` | 6 reviewer configs with system prompts, `run_review_roundtable()` parallel dispatch function |

### Modified files

| File | Changes |
|------|---------|
| `backend/app/services/paper_pipeline_v2.py` | Replace `_phase_merge()` with `_phase_roundtable_review()`, update `generate_paper_v2()` call site |
| `backend/app/schemas/paper.py` | Add `ReviewerFeedback` schema, add `roundtable_reviews` to `PaperGenerateV2Response` |
| `frontend/lib/types.ts` | Add `ReviewerFeedback` interface, add field to `PaperGenerateV2Response` |
| `frontend/app/projects/[projectId]/research/paper/page.tsx` | Display roundtable reviews in results |

---

## Task 1: Reviewer Registry

**Files:**
- Create: `backend/app/services/paper_reviewers.py`

- [ ] **Step 1: Create the reviewer registry module**

Contains 6 reviewer configs with full system prompts and the parallel dispatch function.

```python
"""
Paper roundtable reviewer registry.

6 named reviewers modeled after prominent academics, each with a unique
reviewing philosophy. Used in Phase 3 of the v2 paper pipeline.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services.agents import AgentLog, NamedAgent, extract_json
from app.services.ai_client import get_cloud_client, OpenAIClient
from app.config import settings

logger = logging.getLogger(__name__)

MIN_SCORE_FOR_PASS = 7
MAX_ROUNDTABLE_ROUNDS = 2


@dataclass
class ReviewerConfig:
    id: str
    name: str
    modeled_after: str
    focus: str
    system_prompt: str


_OUTPUT_SUFFIX = """
OUTPUT FORMAT — respond with ONLY a JSON object (no markdown fences):
{
    "score": <1-10>,
    "strengths": ["strength 1", "strength 2"],
    "weaknesses": ["weakness 1", "weakness 2"],
    "suggestions": ["suggestion 1", "suggestion 2"],
    "critical_issues": ["issue 1"]
}

Score strictly:
- 9-10: Publication-ready, exceptional work
- 7-8: Good, minor revisions needed
- 5-6: Major revisions required
- 1-4: Fundamental problems

Be specific: quote passages, reference section numbers, give concrete examples of issues."""


_TECHNICAL_RIGOR_PROMPT = (
    "You are a peer reviewer modeled after Yoshua Bengio's reviewing style — "
    "deep technical scrutiny, mathematical precision, and a focus on reproducibility.\n\n"
    "YOUR REVIEWING PHILOSOPHY:\n"
    "1. MATHEMATICAL RIGOR — Are all claims formally stated? Are proofs correct? "
    "Are approximations justified? If there are no formal results, is the empirical "
    "methodology sound enough to support the claims?\n\n"
    "2. EXPERIMENTAL METHODOLOGY — Is the experimental setup described precisely enough "
    "to reproduce? Are baselines fair and up-to-date? Are hyperparameters reported? "
    "Is there variance reporting (error bars, confidence intervals)?\n\n"
    "3. CLAIMS VS EVIDENCE — For every claim in the paper, is there sufficient evidence? "
    "Flag overclaiming. 'We achieve state-of-the-art' needs to be backed by comprehensive "
    "benchmarks, not cherry-picked results.\n\n"
    "4. THEORETICAL GROUNDING — Is the method motivated by theory or just empirical tricks? "
    "Does the paper explain WHY the approach works, not just that it works?\n\n"
    "5. REPRODUCIBILITY — Could a competent researcher reproduce the results from the paper "
    "alone? Are all components, datasets, and evaluation protocols described?\n\n"
    "6. LIMITATIONS — Does the paper honestly discuss what doesn't work? Missing limitations "
    "sections are a red flag.\n"
) + _OUTPUT_SUFFIX

_NOVELTY_POSITIONING_PROMPT = (
    "You are a peer reviewer modeled after Yann LeCun's reviewing style — "
    "blunt about novelty, strong opinions on positioning, zero tolerance for overclaiming.\n\n"
    "YOUR REVIEWING PHILOSOPHY:\n"
    "1. GENUINE NOVELTY — What is actually new here? Strip away the framing and ask: "
    "would this change how people think about the problem? Incremental improvements "
    "dressed up as breakthroughs are the most common sin in ML papers.\n\n"
    "2. RELATED WORK COMPLETENESS — Are the most relevant prior works cited? Are they "
    "described accurately and compared fairly? Missing key references is a sign the authors "
    "don't know the field well enough.\n\n"
    "3. POSITIONING HONESTY — Is the paper positioned correctly? Does it overclaim its "
    "contribution? A solid incremental paper is fine — but don't sell it as a paradigm shift.\n\n"
    "4. DIFFERENTIATION — What specifically distinguishes this from the closest prior work? "
    "Can the authors articulate the delta clearly in one paragraph?\n\n"
    "5. SIGNIFICANCE — Will this work matter in 2 years? Does it open new research directions "
    "or is it a dead-end optimization?\n\n"
    "6. HONEST COMPARISON — Are experiments compared against the strongest baselines, "
    "not just straw men? Cherry-picking weak baselines is intellectual dishonesty.\n"
) + _OUTPUT_SUFFIX

_WRITING_CLARITY_PROMPT = (
    "You are a peer reviewer modeled after Steven Pinker's approach to academic writing — "
    "obsessed with clarity, structure, and the reader's experience.\n\n"
    "YOUR REVIEWING PHILOSOPHY:\n"
    "1. ABSTRACT QUALITY — Is the abstract self-contained? Does it state the problem, "
    "approach, key result, and significance in under 200 words? Can someone decide whether "
    "to read the paper from the abstract alone?\n\n"
    "2. LOGICAL FLOW — Does each section follow naturally from the previous one? "
    "Are transitions explicit? Can you trace the argument from introduction to conclusion "
    "without gaps?\n\n"
    "3. SENTENCE CLARITY — Flag any sentence that requires re-reading. Academic writing "
    "should be precise, not dense. Rewrite unclear passages as concrete suggestions.\n\n"
    "4. JARGON MANAGEMENT — Is every technical term defined on first use? Is domain-specific "
    "vocabulary minimized? Use the simplest word that conveys the meaning.\n\n"
    "5. PARAGRAPH STRUCTURE — Does each paragraph have a clear topic sentence? Are paragraphs "
    "3-6 sentences? Giant paragraphs are a readability failure.\n\n"
    "6. CONCLUSION ALIGNMENT — Does the conclusion deliver on the introduction's promises? "
    "Do the contributions stated in the intro match what was actually demonstrated?\n"
) + _OUTPUT_SUFFIX

_PRACTICAL_IMPACT_PROMPT = (
    "You are a peer reviewer modeled after Andrew Ng's perspective — "
    "bridging research and real-world value, focused on practical applicability.\n\n"
    "YOUR REVIEWING PHILOSOPHY:\n"
    "1. THE 'SO WHAT' TEST — If this paper is correct, what changes in practice? "
    "Who benefits? If the answer is 'nobody outside this niche', the significance "
    "section needs work.\n\n"
    "2. DEPLOYMENT REALITY — Could someone actually use this in production? What are "
    "the computational requirements? Does it need special hardware, rare data, or "
    "unrealistic assumptions?\n\n"
    "3. SCALABILITY — Does the approach scale to real-world data sizes? A method that "
    "works on MNIST but not ImageNet is not a practical contribution.\n\n"
    "4. HONEST LIMITATIONS — Are failure modes documented? What happens at the boundaries? "
    "When does this approach NOT work? Practitioners need this information.\n\n"
    "5. REPRODUCIBILITY FOR PRACTITIONERS — Is there enough detail for an engineer "
    "(not a researcher) to implement this? Are there code/data availability statements?\n\n"
    "6. COST-BENEFIT — Is the improvement worth the added complexity? A 0.5% accuracy "
    "gain that requires 10x more compute is not a practical contribution.\n"
) + _OUTPUT_SUFFIX

_DESIGN_ELEGANCE_PROMPT = (
    "You are a peer reviewer modeled after Saining Xie's design philosophy — "
    "simplicity, elegance, and rigorous justification of every component.\n\n"
    "YOUR REVIEWING PHILOSOPHY:\n"
    "1. SIMPLICITY VS COMPLEXITY — Is every component necessary? Could you remove any "
    "part and still get most of the benefit? The best designs are the simplest ones "
    "that solve the problem.\n\n"
    "2. DESIGN JUSTIFICATION — Is every architectural choice explained and justified? "
    "'We use X because it worked best' is not enough — WHY did it work best? "
    "What principle guided the choice?\n\n"
    "3. ABLATION RIGOR — Are ablation studies comprehensive? Does removing each component "
    "individually show its contribution? Incomplete ablations hide unnecessary complexity.\n\n"
    "4. COMPONENT INTERACTIONS — Are there unexpected interactions between components? "
    "Does the system's behavior depend on specific combinations of design choices?\n\n"
    "5. ELEGANCE — Does the overall design have a coherent philosophy? Or is it a "
    "collection of tricks? A system should have a unifying principle.\n\n"
    "6. MODERNIZATION — Does the paper use modern best practices? Or does it build on "
    "outdated foundations? Are there simpler modern alternatives to the proposed approach?\n"
) + _OUTPUT_SUFFIX

_SCIENCE_COMMUNICATION_PROMPT = (
    "You are a peer reviewer modeled after Eric Topol's science communication style — "
    "passionate about making complex research accessible to broader audiences.\n\n"
    "YOUR REVIEWING PHILOSOPHY:\n"
    "1. ACCESSIBILITY — Can a smart non-specialist understand the main contribution "
    "from the introduction and conclusion? Technical depth in the middle is fine, but "
    "the bookends must be accessible.\n\n"
    "2. NARRATIVE ARC — Does the paper tell a story? Problem → Why it matters → "
    "What we did → What we found → Why it matters (again). A paper without narrative "
    "is a report, not a contribution.\n\n"
    "3. JARGON TRANSLATION — For each piece of technical jargon, ask: is there a "
    "way to say this that a clinical researcher / engineer / policymaker would understand? "
    "Provide alternative phrasings.\n\n"
    "4. BIG-PICTURE FRAMING — Does the paper connect to the broader context? Why should "
    "anyone outside the immediate subfield care? What's the long-term vision?\n\n"
    "5. FIGURE EFFECTIVENESS — Do the figures tell the story independently? Can you "
    "understand the main result from the figures without reading the text?\n\n"
    "6. IMPACT STATEMENT — Is the broader impact discussed? Not just 'our method is fast' "
    "but 'this enables X which helps Y in the real world'.\n"
) + _OUTPUT_SUFFIX


REVIEWER_REGISTRY: Dict[str, ReviewerConfig] = {
    "technical_rigor": ReviewerConfig(
        id="technical_rigor",
        name="Technical Rigor",
        modeled_after="Yoshua Bengio",
        focus="Methodology, math, reproducibility, claims vs evidence",
        system_prompt=_TECHNICAL_RIGOR_PROMPT,
    ),
    "novelty_positioning": ReviewerConfig(
        id="novelty_positioning",
        name="Novelty & Positioning",
        modeled_after="Yann LeCun",
        focus="Novelty, related work, positioning, differentiation",
        system_prompt=_NOVELTY_POSITIONING_PROMPT,
    ),
    "writing_clarity": ReviewerConfig(
        id="writing_clarity",
        name="Writing Clarity",
        modeled_after="Steven Pinker",
        focus="Sentence clarity, structure, flow, abstract quality",
        system_prompt=_WRITING_CLARITY_PROMPT,
    ),
    "practical_impact": ReviewerConfig(
        id="practical_impact",
        name="Practical Impact",
        modeled_after="Andrew Ng",
        focus="Real-world applicability, scalability, limitations",
        system_prompt=_PRACTICAL_IMPACT_PROMPT,
    ),
    "design_elegance": ReviewerConfig(
        id="design_elegance",
        name="Design Elegance",
        modeled_after="Saining Xie",
        focus="Architecture simplicity, component justification, ablations",
        system_prompt=_DESIGN_ELEGANCE_PROMPT,
    ),
    "science_communication": ReviewerConfig(
        id="science_communication",
        name="Science Communication",
        modeled_after="Eric Topol",
        focus="Accessibility, narrative, jargon translation, big-picture",
        system_prompt=_SCIENCE_COMMUNICATION_PROMPT,
    ),
}


def get_reviewer(reviewer_id: str) -> Optional[ReviewerConfig]:
    return REVIEWER_REGISTRY.get(reviewer_id)


def get_all_reviewers() -> List[ReviewerConfig]:
    return list(REVIEWER_REGISTRY.values())


async def run_review_roundtable(
    paper_content: str,
    venue_text: str,
    agent_log: AgentLog,
) -> List[Dict[str, Any]]:
    """
    Dispatch all 6 reviewers in parallel to critique the paper.

    Each reviewer receives the full paper and outputs structured JSON feedback.
    Returns a list of result dicts: [{reviewer_id, reviewer_name, modeled_after,
    focus, score, strengths, weaknesses, suggestions, critical_issues}, ...]
    """
    cloud = get_cloud_client()
    # Use OpenAI for 2 reviewers (cross-model diversity) if available
    if settings.openai_api_key:
        alt_client: Any = OpenAIClient()
    else:
        alt_client = cloud

    # Assign clients: most use cloud, technical_rigor and novelty use alt for diversity
    client_map = {
        "technical_rigor": alt_client,
        "novelty_positioning": alt_client,
        "writing_clarity": cloud,
        "practical_impact": cloud,
        "design_elegance": cloud,
        "science_communication": cloud,
    }

    async def _run_one(reviewer: ReviewerConfig) -> Dict[str, Any]:
        client = client_map.get(reviewer.id, cloud)
        agent = NamedAgent(f"reviewer_{reviewer.id}", client, agent_log)

        user_prompt = (
            f"## Paper to Review\n\n{paper_content}\n\n"
            f"{venue_text}\n\n"
            f"Review this paper from your perspective: {reviewer.focus}\n"
            f"Output your JSON review."
        )

        try:
            data = await agent.complete_json(
                system=reviewer.system_prompt,
                user=user_prompt,
                action="roundtable_review",
                section=f"{reviewer.name} ({reviewer.modeled_after})",
            )
        except Exception:
            logger.exception("Reviewer %s failed", reviewer.id)
            data = {}

        score = data.get("score", 0)
        try:
            score = int(score)
        except (ValueError, TypeError):
            score = 0

        result = {
            "reviewer_id": reviewer.id,
            "reviewer_name": reviewer.name,
            "modeled_after": reviewer.modeled_after,
            "focus": reviewer.focus,
            "score": score,
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "suggestions": data.get("suggestions", []),
            "critical_issues": data.get("critical_issues", []),
        }

        agent_log.add(
            f"reviewer_{reviewer.id}",
            "roundtable_scored",
            f"{reviewer.name} ({reviewer.modeled_after}): {score}/10 — "
            f"{len(result['critical_issues'])} critical, "
            f"{len(result['suggestions'])} suggestions",
            section=f"{reviewer.name}",
            score=score,
        )

        return result

    reviewers = list(REVIEWER_REGISTRY.values())
    tasks = [_run_one(r) for r in reviewers]
    results = await asyncio.gather(*tasks)

    return list(results)


def build_revision_brief(reviews: List[Dict[str, Any]]) -> str:
    """Build a structured revision brief from all reviewer feedback.

    The writer receives this as context for revising the paper.
    """
    lines: List[str] = ["## Roundtable Review Summary\n"]

    # Per-reviewer summaries
    for r in reviews:
        lines.append(f"### {r['reviewer_name']} ({r['modeled_after']}) — {r['score']}/10")
        lines.append(f"Focus: {r['focus']}\n")
        if r["strengths"]:
            lines.append("**Strengths:**")
            for s in r["strengths"]:
                lines.append(f"- {s}")
        if r["critical_issues"]:
            lines.append("\n**Critical Issues (must fix):**")
            for ci in r["critical_issues"]:
                lines.append(f"- {ci}")
        if r["suggestions"]:
            lines.append("\n**Suggestions:**")
            for s in r["suggestions"]:
                lines.append(f"- {s}")
        if r["weaknesses"]:
            lines.append("\n**Weaknesses:**")
            for w in r["weaknesses"]:
                lines.append(f"- {w}")
        lines.append("")

    # Priority guide
    all_critical = []
    all_suggestions = []
    for r in reviews:
        for ci in r.get("critical_issues", []):
            all_critical.append(f"[{r['reviewer_name']}] {ci}")
        for s in r.get("suggestions", []):
            all_suggestions.append(f"[{r['reviewer_name']}] {s}")

    lines.append("### Priority Revision Guide")
    if all_critical:
        lines.append("\n**Critical issues (MUST fix):**")
        for ci in all_critical:
            lines.append(f"1. {ci}")
    if all_suggestions:
        lines.append("\n**Important suggestions:**")
        for s in all_suggestions[:10]:  # cap at 10
            lines.append(f"- {s}")

    avg_score = sum(r["score"] for r in reviews) / len(reviews) if reviews else 0
    lines.append(f"\n**Average score: {avg_score:.1f}/10**")

    return "\n".join(lines)
```

- [ ] **Step 2: Verify module imports**

```bash
docker compose exec backend python -c "from app.services.paper_reviewers import REVIEWER_REGISTRY, run_review_roundtable, build_revision_brief; print(f'OK: {len(REVIEWER_REGISTRY)} reviewers')"
```
Expected: `OK: 6 reviewers`

---

## Task 2: Replace Phase 3 in Pipeline

**Files:**
- Modify: `backend/app/services/paper_pipeline_v2.py`

- [ ] **Step 1: Add import for paper_reviewers**

Add to the imports at the top of `paper_pipeline_v2.py`:
```python
from app.services.paper_reviewers import (
    run_review_roundtable,
    build_revision_brief,
    MIN_SCORE_FOR_PASS,
    MAX_ROUNDTABLE_ROUNDS,
)
```

- [ ] **Step 2: Replace `_phase_merge()` with `_phase_roundtable_review()`**

Replace the entire `_phase_merge()` function (from `async def _phase_merge(` to `return coherent_paper` before the Phase 4 comment) with:

```python
async def _phase_roundtable_review(
    agents: Dict[str, NamedAgent],
    sections: List[Dict],
    written_sections: Dict[str, str],
    venue: Optional[VenueGuidelines],
) -> Tuple[str, List[Dict]]:
    """Phase 3: Assemble, coherence pass, roundtable review, revision.

    Returns (final_paper_content, roundtable_reviews).
    """
    editor = agents["gemini_editor"]
    writer = agents["gemini_writer"]
    agent_log = editor.log
    venue_text = _venue_block(venue)

    # --- Step 1: Assemble sections ---
    assembled_parts: List[str] = []
    for section in sections:
        sec_num = str(section["number"])
        sec_title = section.get("title", f"Section {sec_num}")
        content = written_sections.get(sec_num, "")
        if content:
            assembled_parts.append(content)
        else:
            assembled_parts.append(f"## {sec_num}. {sec_title}\n\n[Section not generated]")

    assembled = "\n\n".join(assembled_parts)

    # --- Step 2: Coherence pass ---
    coherence_user = (
        f"## Full Paper\n{assembled}\n\n"
        f"{venue_text}\n\n"
        "Perform a coherence pass: smooth transitions, normalize terminology, "
        "fix inconsistencies. Output the COMPLETE paper."
    )
    paper = await editor.complete(
        system=_EDITOR_COHERENCE_SYSTEM,
        user=coherence_user,
        action="coherence_pass",
    )

    # --- Step 3: Condense if over budget ---
    if venue and venue.page_limit:
        estimated = _estimate_pages(paper)
        budget_threshold = venue.page_limit * 1.15
        if estimated > budget_threshold:
            agent_log.add(
                "gemini_editor", "condense_triggered",
                f"Paper is ~{estimated} pages, budget is {venue.page_limit}. Condensing.",
            )
            condense_user = (
                f"## Full Paper\n{paper}\n\n"
                f"Target: {venue.page_limit} pages (~{venue.page_limit * 300} words).\n"
                f"{venue_text}\n\n"
                "Condense the paper to fit. Output the COMPLETE paper."
            )
            paper = await editor.complete(
                system=_EDITOR_CONDENSE_SYSTEM,
                user=condense_user,
                action="condense_pass",
            )

    # --- Step 4: Roundtable review (up to MAX_ROUNDTABLE_ROUNDS) ---
    all_reviews: List[Dict] = []
    for round_num in range(1, MAX_ROUNDTABLE_ROUNDS + 1):
        agent_log.add(
            "system", "roundtable_start",
            f"Roundtable review round {round_num}/{MAX_ROUNDTABLE_ROUNDS}",
        )

        reviews = await run_review_roundtable(paper, venue_text, agent_log)
        all_reviews = reviews  # keep latest round

        # Build revision brief
        brief = build_revision_brief(reviews)
        min_score = min(r["score"] for r in reviews) if reviews else 0
        avg_score = sum(r["score"] for r in reviews) / len(reviews) if reviews else 0

        agent_log.add(
            "system", "roundtable_complete",
            f"Round {round_num}: avg {avg_score:.1f}/10, min {min_score}/10, "
            f"{sum(len(r.get('critical_issues', [])) for r in reviews)} critical issues",
        )

        # --- Step 5: Writer revises based on roundtable feedback ---
        revision_user = (
            f"## Paper to Revise\n\n{paper}\n\n"
            f"{brief}\n\n"
            f"{venue_text}\n\n"
            "Address ALL critical issues and as many suggestions as feasible. "
            "Return the COMPLETE revised paper."
        )
        paper = await writer.complete(
            system=_WRITER_REVISE_SYSTEM,
            user=revision_user,
            action="roundtable_revision",
            section=f"round_{round_num}",
        )

        # If all reviewers scored >= MIN_SCORE_FOR_PASS, no need for another round
        if min_score >= MIN_SCORE_FOR_PASS:
            agent_log.add(
                "system", "roundtable_passed",
                f"All reviewers scored >= {MIN_SCORE_FOR_PASS}, skipping additional rounds",
            )
            break

    return paper, all_reviews
```

- [ ] **Step 3: Update the `generate_paper_v2()` call site**

In `generate_paper_v2()`, find where `_phase_merge()` is called (around line 690-695):

```python
    final_content = await _phase_merge(
        agents["gemini_editor"], agents["openai_critic"],
        sections, written_sections, venue,
    )
```

Replace with:

```python
    final_content, roundtable_reviews = await _phase_roundtable_review(
        agents, sections, written_sections, venue,
    )
```

Then in the return dict at the end of `generate_paper_v2()`, add `roundtable_reviews`:

Find:
```python
        "venue_guidelines": venue.to_dict() if venue else None,
    }
```

Replace with:
```python
        "venue_guidelines": venue.to_dict() if venue else None,
        "roundtable_reviews": [
            {
                "reviewer_id": r["reviewer_id"],
                "reviewer_name": r["reviewer_name"],
                "modeled_after": r.get("modeled_after", ""),
                "focus": r["focus"],
                "score": r["score"],
                "strengths": r.get("strengths", []),
                "weaknesses": r.get("weaknesses", []),
                "suggestions": r.get("suggestions", []),
                "critical_issues": r.get("critical_issues", []),
            }
            for r in roundtable_reviews
        ],
    }
```

- [ ] **Step 4: Verify imports work**

```bash
docker compose exec backend python -c "from app.services.paper_pipeline_v2 import generate_paper_v2; print('OK')"
```

---

## Task 3: Schemas + Types

**Files:**
- Modify: `backend/app/schemas/paper.py`
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Add ReviewerFeedback schema to backend**

Add to `backend/app/schemas/paper.py` after `PaperEditResponse`:

```python
class ReviewerFeedback(BaseModel):
    reviewer_id: str
    reviewer_name: str
    modeled_after: str
    focus: str
    score: int
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    critical_issues: List[str] = Field(default_factory=list)
```

- [ ] **Step 2: Add `roundtable_reviews` to `PaperGenerateV2Response`**

In the existing `PaperGenerateV2Response` class, add after `venue_guidelines`:

```python
    roundtable_reviews: Optional[List[ReviewerFeedback]] = None
```

- [ ] **Step 3: Update the router to pass roundtable_reviews**

In `backend/app/routers/paper.py`, find the `generate_paper_v2` endpoint where it constructs `PaperGenerateV2Response`. Add the import:

```python
from app.schemas.paper import (
    # ... existing imports ...
    ReviewerFeedback,
)
```

And add to the response construction:

```python
        roundtable_reviews=[
            ReviewerFeedback(**r) for r in result.get("roundtable_reviews", [])
        ] if result.get("roundtable_reviews") else None,
```

- [ ] **Step 4: Add frontend types**

In `frontend/lib/types.ts`, add after the `PaperEditResponse` interface:

```typescript
export interface ReviewerFeedback {
  reviewer_id: string;
  reviewer_name: string;
  modeled_after: string;
  focus: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  critical_issues: string[];
}
```

Add to `PaperGenerateV2Response`:

```typescript
  roundtable_reviews?: ReviewerFeedback[] | null;
```

---

## Task 4: Frontend Display

**Files:**
- Modify: `frontend/app/projects/[projectId]/research/paper/page.tsx`

- [ ] **Step 1: Add roundtable review display**

In the paper results section, after the existing agent log viewer, add a roundtable review panel. This shows each reviewer's feedback as a card with score badge, strengths, weaknesses, and critical issues.

Add `ReviewerFeedback` to the type import from `@/lib/types`.

Add state to track roundtable reviews:
```typescript
const [roundtableReviews, setRoundtableReviews] = useState<ReviewerFeedback[]>([]);
```

In the generate handler, after setting agentLog from v2 response, add:
```typescript
if ("roundtable_reviews" in res && (res as PaperGenerateV2Response).roundtable_reviews) {
  setRoundtableReviews((res as PaperGenerateV2Response).roundtable_reviews || []);
}
```

Add this JSX after the agent log `<details>` element:

```tsx
{/* Roundtable Review Panel */}
{roundtableReviews.length > 0 && (
  <details className="mb-4 border rounded-lg" open>
    <summary className="p-3 cursor-pointer flex items-center gap-2 font-medium text-sm hover:bg-secondary/30 rounded-lg transition-colors">
      <Users className="h-4 w-4 text-violet-400" />
      Roundtable Review ({roundtableReviews.length} reviewers, avg {(roundtableReviews.reduce((s, r) => s + r.score, 0) / roundtableReviews.length).toFixed(1)}/10)
    </summary>
    <div className="p-3 space-y-3 border-t">
      {roundtableReviews.map((r) => (
        <div key={r.reviewer_id} className="border rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-semibold">{r.reviewer_name}</span>
              <span className="text-xs text-muted-foreground ml-2">({r.modeled_after})</span>
            </div>
            <Badge variant={r.score >= 8 ? "default" : r.score >= 7 ? "outline" : "destructive"} className="text-xs">
              {r.score}/10
            </Badge>
          </div>
          <p className="text-[11px] text-muted-foreground">{r.focus}</p>
          {r.critical_issues.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-red-400">Critical Issues:</p>
              <ul className="text-xs text-muted-foreground list-disc list-inside">
                {r.critical_issues.map((ci, i) => <li key={i}>{ci}</li>)}
              </ul>
            </div>
          )}
          {r.strengths.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-green-400">Strengths:</p>
              <ul className="text-xs text-muted-foreground list-disc list-inside">
                {r.strengths.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {r.suggestions.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-amber-400">Suggestions:</p>
              <ul className="text-xs text-muted-foreground list-disc list-inside">
                {r.suggestions.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
        </div>
      ))}
    </div>
  </details>
)}
```

- [ ] **Step 2: Verify frontend builds**

```bash
cd frontend && npm run build
```

---

## Task 5: Integration Verification

- [ ] **Step 1: Rebuild backend**
```bash
docker compose up --build -d backend
```

- [ ] **Step 2: Verify reviewer registry**
```bash
docker compose exec backend python -c "from app.services.paper_reviewers import REVIEWER_REGISTRY; print(f'{len(REVIEWER_REGISTRY)} reviewers: {list(REVIEWER_REGISTRY.keys())}')"
```

- [ ] **Step 3: Run test suite**
```bash
docker compose exec backend bash -c "cd /app/tests && python -m pytest test_endpoints.py -v"
```

---

## Summary

| Task | Component | Files | Complexity |
|------|-----------|-------|-----------|
| 1 | Reviewer Registry | Create: `paper_reviewers.py` | High (6 prompts + dispatch) |
| 2 | Pipeline Phase 3 | Modify: `paper_pipeline_v2.py` | Medium (replace function + call site) |
| 3 | Schemas + Types | Modify: `paper.py`, `types.ts`, `paper.py` (router) | Low |
| 4 | Frontend Display | Modify: `page.tsx` | Medium |
| 5 | Verification | No code | Low |

Total: 1 new file, 5 modified files.
