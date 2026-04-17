"""
Tests for paper_pipeline_v2 — the multi-agent paper generator.

Scope: pure helpers + the PLAN phase (which is the smallest testable
unit that exercises real pipeline logic: JSON parsing, fallback-to-
default-outline, venue-aware page-budget rescaling).

The DRAFT / ROUNDTABLE / FINALIZE phases are intentionally NOT covered
here — they each fan out to multiple AI calls and mocking them
faithfully would require reproducing the whole review loop. Start with
this and grow coverage as real bugs surface.
"""
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

from app.services import paper_pipeline_v2 as pp
from app.services.agents import AgentLog
from app.services.venue_service import VenueGuidelines


# ---------- Pure helpers ---------------------------------------------------


class TestSafeScore:
    def test_int_passthrough(self):
        assert pp._safe_score(8) == 8

    def test_string_digit(self):
        assert pp._safe_score("7") == 7

    def test_float_truncates(self):
        # int(8.9) == 8 — documents that fractional scores drop the decimal
        assert pp._safe_score(8.9) == 8

    def test_non_numeric_returns_zero(self):
        assert pp._safe_score("not a score") == 0
        assert pp._safe_score(None) == 0
        assert pp._safe_score({"score": 8}) == 0


class TestVenueBlock:
    def test_none_venue_returns_empty(self):
        assert pp._venue_block(None) == ""

    def test_venue_without_constraints_returns_empty(self):
        # venue exists but has neither page_limit nor word_limit
        v = VenueGuidelines(venue_name="Arxiv")
        assert pp._venue_block(v) == ""

    def test_page_limit_appears_in_block(self):
        v = VenueGuidelines(venue_name="NeurIPS", page_limit=9, template="neurips")
        block = pp._venue_block(v)
        assert "Target venue: NeurIPS" in block
        assert "Page limit: 9" in block
        assert "Template: neurips" in block

    def test_word_limit_without_page_limit(self):
        v = VenueGuidelines(venue_name="Nature", word_limit=4000)
        block = pp._venue_block(v)
        assert "Word limit: 4000" in block
        assert "Page limit" not in block

    def test_anonymization_flag_rendered(self):
        v = VenueGuidelines(
            venue_name="ICML", page_limit=8, anonymization=True, topics=["ML", "RL"],
        )
        block = pp._venue_block(v)
        assert "Anonymization: required (double-blind)" in block
        assert "Topics: ML, RL" in block


class TestProgressTags:
    def test_basic_percentage(self):
        tags = pp._progress_tags("plan", 1, 4)
        assert "paper" in tags
        assert "v2" in tags
        assert "progress:25" in tags
        assert "step:plan" in tags

    def test_caps_at_99_when_complete(self):
        # Intentionally never hits 100 — frontend polling treats 100 as "done
        # from the other side", so the pipeline never announces that itself
        tags = pp._progress_tags("draft", 10, 10)
        assert "progress:99" in tags

    def test_zero_total_does_not_divide_by_zero(self):
        # Defensive: early-pipeline states where total isn't known yet
        tags = pp._progress_tags("plan", 0, 0)
        assert any(t.startswith("progress:") for t in tags)


class TestEstimatePages:
    def test_empty_text_is_zero(self):
        assert pp._estimate_pages("") == 0

    def test_single_word_is_basically_zero(self):
        assert pp._estimate_pages("word") == 0

    def test_300_words_is_one_page(self):
        text = " ".join(["word"] * 300)
        assert pp._estimate_pages(text) == 1.0

    def test_900_words_is_three_pages(self):
        text = " ".join(["word"] * 900)
        assert pp._estimate_pages(text) == 3.0


class TestFindSectionTitle:
    def test_found_by_string_number(self):
        sections = [{"number": "2", "title": "Background"}, {"number": "3", "title": "Methods"}]
        assert pp._find_section_title(sections, "2") == "Background"

    def test_found_with_numeric_number_in_outline(self):
        # Outline may come back with int numbers — defensive string-coerce
        sections = [{"number": 2, "title": "Background"}]
        assert pp._find_section_title(sections, "2") == "Background"

    def test_missing_returns_default(self):
        sections = [{"number": "1", "title": "Intro"}]
        assert pp._find_section_title(sections, "99") == "Section 99"

    def test_missing_title_field_falls_back(self):
        # Outline entry without a title at all
        sections = [{"number": "1"}]
        assert pp._find_section_title(sections, "1") == "Section 1"


# ---------- _phase_plan integration ----------------------------------------
#
# _phase_plan is the plan-phase orchestrator. It's the simplest phase to
# test because it only makes one AI call. We fake the agent so the test
# is deterministic and doesn't hit a real provider.


class FakeAgent:
    """Drop-in for NamedAgent that returns a canned JSON payload.

    Only `complete_json` is called by _phase_plan. Keeping this narrow —
    if paper_pipeline_v2 grows to call other methods, the test will
    break loudly instead of silently misbehaving.
    """

    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload
        self.log = AgentLog()
        self.calls = 0

    async def complete_json(
        self, system: str, user: str, action: str = "complete_json",
        section: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.calls += 1
        self._last_user = user  # let tests assert what was sent
        return self._payload


@pytest.mark.asyncio
async def test_phase_plan_returns_agent_outline_when_well_formed():
    agent = FakeAgent({
        "sections": [
            {"number": "1", "title": "Intro", "pages": 1.0, "depends_on": [], "key_points": ["a"]},
            {"number": "2", "title": "Body", "pages": 2.0, "depends_on": ["1"], "key_points": ["b"]},
        ],
        "total_pages": 3,
    })

    result = await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="Test paper",
        paper_type="research",
        context_block="some project context",
        venue=None,
    )

    assert agent.calls == 1
    assert len(result) == 2
    assert result[0]["title"] == "Intro"
    assert result[1]["title"] == "Body"


@pytest.mark.asyncio
async def test_phase_plan_falls_back_to_default_outline_when_empty():
    # Planner returned valid JSON but no sections — we should use the
    # built-in 6-section default, not propagate the empty list.
    agent = FakeAgent({"sections": []})

    result = await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="Test paper",
        paper_type="research",
        context_block="ctx",
        venue=None,
    )

    assert len(result) == len(pp._DEFAULT_OUTLINE)
    assert result[0]["title"] == "Introduction"
    assert result[-1]["title"] == "Conclusion"


@pytest.mark.asyncio
async def test_phase_plan_falls_back_when_sections_is_not_a_list():
    # Planner hallucinates a non-list (dict, string, number). Code path
    # explicitly guards on isinstance(..., list).
    agent = FakeAgent({"sections": {"bogus": "shape"}})

    result = await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="Test", paper_type="research", context_block="", venue=None,
    )

    assert len(result) == len(pp._DEFAULT_OUTLINE)


@pytest.mark.asyncio
async def test_phase_plan_rescales_default_outline_to_venue_page_limit():
    # When the planner gives us nothing but the venue demands a specific
    # page count, the fallback outline's budgets must be rescaled so
    # they sum to that limit. Otherwise downstream phase_draft would
    # happily overshoot the venue's cap.
    agent = FakeAgent({"sections": []})
    venue = VenueGuidelines(venue_name="ICML", page_limit=8)

    result = await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="Test", paper_type="research", context_block="", venue=venue,
    )

    total = sum(s["pages"] for s in result)
    # Default sums to 8.0 already (1.5+1.5+2.0+1.5+1.0+0.5), so rescale
    # to 8 is a no-op in this case — but also test that rescaling ran by
    # setting a different page_limit.
    assert len(result) == len(pp._DEFAULT_OUTLINE)
    # Allow small rounding drift since _phase_plan rounds to 1 decimal.
    assert abs(total - 8) < 0.5


@pytest.mark.asyncio
async def test_phase_plan_rescales_default_outline_to_short_venue():
    agent = FakeAgent({"sections": []})
    venue = VenueGuidelines(venue_name="ShortVenue", page_limit=4)

    result = await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="Test", paper_type="research", context_block="", venue=venue,
    )

    total = sum(s["pages"] for s in result)
    # Default sums to 8; rescaled to 4 should be roughly half.
    # Each page is rounded to 1 decimal so drift can be up to 0.3 across 6.
    assert abs(total - 4) < 0.5


@pytest.mark.asyncio
async def test_phase_plan_prompt_includes_venue_constraints():
    # The planner needs to SEE the venue constraints or it'll ignore
    # them. Verifying that _phase_plan threads them into the user prompt.
    agent = FakeAgent({
        "sections": [
            {"number": "1", "title": "Intro", "pages": 1.0, "depends_on": [], "key_points": []},
        ],
    })
    venue = VenueGuidelines(venue_name="NeurIPS", page_limit=9, template="neurips")

    await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="Paper A", paper_type="research",
        context_block="project context here", venue=venue,
    )

    sent = agent._last_user
    assert "NeurIPS" in sent
    assert "Page limit: 9" in sent
    # Hard constraint sentence is intentionally emphatic — regression
    # guard against dropping the MUST from the prompt.
    assert "MUST be exactly 9 pages" in sent


@pytest.mark.asyncio
async def test_phase_plan_context_is_truncated_to_6000_chars():
    # Large project contexts get sliced to keep prompt-token cost
    # bounded. Regression guard: not shipping all 20k chars to the
    # planner when the user has a fat narrative. If this limit
    # changes, update here + in _phase_plan's slice, not just one.
    big_context = "x" * 20_000
    agent = FakeAgent({
        "sections": [
            {"number": "1", "title": "Intro", "pages": 1.0, "depends_on": [], "key_points": []},
        ],
    })

    await pp._phase_plan(
        planner=agent,  # type: ignore[arg-type]
        title="T", paper_type="research", context_block=big_context, venue=None,
    )

    # Template can add a handful of `x` chars (e.g. "exactly", "text"),
    # so allow a small wiggle above the 6000 slice but reject anything
    # that would mean the full 20k context leaked through.
    x_count = agent._last_user.count("x")
    assert 5_900 <= x_count <= 6_100, f"expected ~6000, got {x_count}"
