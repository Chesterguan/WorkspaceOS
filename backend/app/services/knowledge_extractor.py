"""Knowledge extractor — pulls structured nodes from roundtable turns.

See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


_CLASSIFIER_SYSTEM = (
    "You are a precision classifier. Reply with exactly one word: YES or NO. "
    "Nothing else."
)
_CLASSIFIER_TEMPLATE = (
    "Does this conversation turn contain extractable knowledge?\n"
    "Extractable = states a decision, claim, hypothesis, question to revisit, "
    "rejection, blocker, or insight.\n"
    "NOT extractable = greeting, acknowledgment, restating provided context, "
    "pure question with no answer.\n\n"
    "USER: {user}\n\nAI: {ai}\n\n"
    "Reply YES or NO."
)


async def _classify_extractable(ai: Any, user: str, ai_response: str) -> bool:
    """Stage 1: cheap YES/NO check. Anything that doesn't normalize to YES → False."""
    try:
        raw = await ai.complete(
            _CLASSIFIER_SYSTEM,
            _CLASSIFIER_TEMPLATE.format(user=user[:1500], ai=ai_response[:3000]),
        )
    except Exception:
        logger.exception("knowledge classifier failed")
        return False
    token = (raw or "").strip().rstrip(".").upper()
    return token == "YES"
