"""
Agent abstraction layer for Paper Pipeline v2.

Provides named agent wrappers with structured logging so every LLM call is
traceable through the pipeline (agent name, action, section, score, timestamp).

Usage
-----
    log = AgentLog()
    agents = create_pipeline_agents(log)
    result = await agents["gemini_writer"].complete(system_prompt, user_prompt, section="intro")
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.ai_client import OpenAIClient, get_cloud_client, get_local_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider / model detection helpers for usage logging
# ---------------------------------------------------------------------------

def _detect_provider(client) -> str:
    """Detect which AI provider a client uses."""
    cls_name = type(client).__name__.lower()
    if "openai" in cls_name:
        return "openai"
    if "anthropic" in cls_name:
        return "anthropic"
    if "ollama" in cls_name:
        return "ollama"
    if "gemini" in cls_name:
        return "gemini"
    return "gemini"  # default (GeminiClient is the cloud default)


def _detect_model(client) -> str:
    """Detect which model a client uses."""
    # GeminiClient stores _model; OllamaClient stores chat_model
    if hasattr(client, "_model"):
        return str(client._model)
    if hasattr(client, "chat_model"):
        return str(client.chat_model)
    cls_name = type(client).__name__.lower()
    if "openai" in cls_name:
        return settings.openai_chat_model
    if "anthropic" in cls_name:
        return settings.anthropic_chat_model
    return settings.gemini_chat_model


# ---------------------------------------------------------------------------
# AgentLog — structured collector for pipeline trace entries
# ---------------------------------------------------------------------------

class AgentLog:
    """Collects structured log entries from every agent action in the pipeline."""

    def __init__(self) -> None:
        self.entries: List[Dict] = []

    def add(
        self,
        agent: str,
        action: str,
        detail: str,
        section: Optional[str] = None,
        score: Optional[int] = None,
    ) -> None:
        """Append a log entry with an ISO timestamp."""
        entry: Dict = {
            "agent": agent,
            "action": action,
            "section": section,
            "detail": detail,
            "score": score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.entries.append(entry)
        logger.debug("[%s] %s — %s", agent, action, detail[:120])

    def to_list(self) -> List[Dict]:
        """Return a copy of all log entries."""
        return list(self.entries)


# ---------------------------------------------------------------------------
# extract_json — standalone JSON extractor for AI output
# ---------------------------------------------------------------------------

def extract_json(text: str) -> Dict:
    """Extract a JSON object from AI output that may contain markdown or prose.

    Tries three strategies in order:
      1. Direct parse of the full text (fast path for clean responses).
      2. Strip ```json ... ``` or ``` ... ``` fences, then parse.
      3. Find the first {...} block and parse only that substring.

    Returns an empty dict if none of the strategies succeed.
    """
    # Strategy 1 — direct parse
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 2 — strip markdown fences
    fence_pattern = r"```(?:json)?\s*\n?(.*?)```"
    match = re.search(fence_pattern, stripped, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3 — find first {...} block (handles leading prose)
    brace_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("extract_json: could not parse JSON from text (first 200 chars): %s", text[:200])
    return {}


# ---------------------------------------------------------------------------
# NamedAgent — AI client wrapper with logging
# ---------------------------------------------------------------------------

class NamedAgent:
    """Wraps an AI client with a name for structured pipeline logging."""

    def __init__(self, name: str, client: Any, log: AgentLog) -> None:
        self.name = name
        self.client = client
        self.log = log

    async def complete(
        self,
        system: str,
        user: str,
        action: str = "complete",
        section: Optional[str] = None,
    ) -> str:
        """Call the underlying client and log the result.

        Returns the raw text response from the AI provider.
        """
        result: str = await self.client.complete(system, user)
        # Log a brief excerpt so the trace is readable without being huge.
        detail = result[:200].replace("\n", " ")
        self.log.add(self.name, action, detail, section=section)
        # Usage logging happens in AIClient.complete() base class — no duplicate here
        return result

    async def complete_json(
        self,
        system: str,
        user: str,
        action: str = "complete_json",
        section: Optional[str] = None,
    ) -> Dict:
        """Call complete() and parse the result as JSON.

        Uses extract_json() to handle markdown fences and leading prose.
        Returns an empty dict if the response cannot be parsed as JSON.
        """
        raw = await self.complete(system, user, action=action, section=section)
        return extract_json(raw)


# ---------------------------------------------------------------------------
# create_pipeline_agents — factory for the 5 standard pipeline agents
# ---------------------------------------------------------------------------

def create_pipeline_agents(agent_log: AgentLog) -> Dict[str, NamedAgent]:
    """Create the five named agents used in the Paper Pipeline v2.

    Agent roles:
      gemini_planner    — outline and section planning (cloud)
      gemini_writer     — drafting and revision (cloud)
      openai_critic     — peer review critique (OpenAI if available, else cloud)
      gemini_editor     — editing and condensing (cloud)
      ollama_literature — literature retrieval and local analysis (local)

    Using OpenAI as the critic when available ensures the reviewer is a
    genuinely different model from the Gemini writer (avoids self-review bias).
    """
    cloud = get_cloud_client()
    local = get_local_client()

    # Critic: prefer OpenAI for genuine cross-model critique
    if settings.openai_api_key:
        critic_client: Any = OpenAIClient()
    else:
        critic_client = cloud

    return {
        "gemini_planner": NamedAgent("gemini_planner", cloud, agent_log),
        "gemini_writer": NamedAgent("gemini_writer", cloud, agent_log),
        "openai_critic": NamedAgent("openai_critic", critic_client, agent_log),
        "gemini_editor": NamedAgent("gemini_editor", cloud, agent_log),
        "ollama_literature": NamedAgent("ollama_literature", local, agent_log),
    }
