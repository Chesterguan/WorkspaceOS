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


import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any

from app.models.knowledge import NODE_TYPES, EDGE_TYPES


@dataclass
class ExtractedNode:
    node_type: str
    title: str
    content: str
    confidence: float = 0.7


@dataclass
class ExtractionResult:
    nodes: List[ExtractedNode] = field(default_factory=list)
    edges_within_turn: List[Dict[str, Any]] = field(default_factory=list)


_EXTRACTION_SYSTEM = (
    "You extract structured knowledge from conversation turns. "
    "Output ONLY valid JSON, no prose, no fences. "
    "Schema:\n"
    '{"nodes":[{"node_type":"<one of: claim|decision|question|hypothesis|rejection|blocker|insight>",'
    '"title":"<=120 chars","content":"1-3 sentences","confidence":0..1,'
    '"rationale":"why this type"}],'
    '"edges_within_turn":[{"from_idx":int,"to_idx":int,'
    '"edge_type":"<one of: supports|contradicts|refines|follows_up|depends_on|derives_from|rejects|related_to>"}]}'
    "\nIf nothing meaningful, return {\"nodes\":[],\"edges_within_turn\":[]}."
)


def _build_extraction_user(user: str, ai_response: str, kind: str,
                           recent_turns: List[Dict[str, str]]) -> str:
    history = ""
    if recent_turns:
        lines = [f"{t['role'].upper()}: {t['content'][:400]}" for t in recent_turns[-5:]]
        history = "## Recent context\n" + "\n".join(lines) + "\n\n"
    bias = (
        "This is a Co-Founder roundtable; expect more decisions/rejections/insights."
        if kind == "cofounder"
        else "This is an academic Research roundtable; expect more claims/hypotheses/questions."
    )
    return (
        f"{history}{bias}\n\n"
        f"## Current turn\nUSER: {user[:2000]}\n\nAI: {ai_response[:4000]}\n\n"
        "Extract any extractable nodes per the schema."
    )


def _strip_json_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s


async def _extract_structured(
    ai: Any, user: str, ai_response: str, conversation_kind: str,
    recent_turns: List[Dict[str, str]],
) -> ExtractionResult:
    """Stage 2. JSON parse failure → empty result, never raises."""
    try:
        raw = await ai.complete(
            _EXTRACTION_SYSTEM,
            _build_extraction_user(user, ai_response, conversation_kind, recent_turns),
        )
    except Exception:
        logger.exception("knowledge structured extraction failed")
        return ExtractionResult()

    try:
        data = json.loads(_strip_json_fences(raw))
    except (ValueError, TypeError):
        logger.warning("knowledge extractor: non-JSON output, dropping. raw=%r", raw[:300])
        return ExtractionResult()

    nodes: List[ExtractedNode] = []
    for n in data.get("nodes", []):
        if not isinstance(n, dict):
            continue
        nt = n.get("node_type")
        if nt not in NODE_TYPES:
            continue
        title = (n.get("title") or "")[:160].strip()
        content = (n.get("content") or "").strip()
        if not title or not content:
            continue
        nodes.append(ExtractedNode(
            node_type=nt, title=title, content=content,
            confidence=float(n.get("confidence", 0.7)),
        ))

    edges: List[Dict[str, Any]] = []
    for e in data.get("edges_within_turn", []):
        if not isinstance(e, dict):
            continue
        et = e.get("edge_type")
        if et not in EDGE_TYPES:
            continue
        try:
            from_idx = int(e["from_idx"])
            to_idx = int(e["to_idx"])
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= from_idx < len(nodes) and 0 <= to_idx < len(nodes) and from_idx != to_idx:
            edges.append({"from_idx": from_idx, "to_idx": to_idx, "edge_type": et})

    return ExtractionResult(nodes=nodes, edges_within_turn=edges)
