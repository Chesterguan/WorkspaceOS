"""
AI client abstraction with hybrid provider support.

Supports a split architecture:
  - "local" client (Ollama) for privacy-sensitive operations: embeddings, extraction, consolidation
  - "cloud" client (Gemini/OpenAI/Anthropic) for quality-sensitive operations: draft writing, blog generation

Configure via env vars:
  LOCAL_AI_PROVIDER=ollama       (default)
  CLOUD_AI_PROVIDER=gemini       (or openai, anthropic, ollama)
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AIClient(ABC):
    """Base class defining the interface every AI provider must implement."""

    @abstractmethod
    async def _do_complete(self, system: str, user: str) -> str:
        ...

    async def complete(self, system: str, user: str) -> str:
        """Call the AI and log usage (fire-and-forget)."""
        result = await self._do_complete(system, user)
        try:
            import asyncio
            from app.services.usage_service import log_usage_standalone
            provider = type(self).__name__.lower().replace("client", "")
            model = getattr(self, "_model", None) or getattr(self, "chat_model", None) or provider
            asyncio.create_task(
                log_usage_standalone(provider, str(model), "complete", system + user, result)
            )
        except Exception:
            pass  # usage logging must never break AI calls
        return result

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        ...


class OpenAIClient(AIClient):
    def __init__(self) -> None:
        import openai
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def _do_complete(self, system: str, user: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    async def embed(self, text: str) -> List[float]:
        truncated = text[:8000]
        response = await self._client.embeddings.create(
            model=settings.openai_embedding_model,
            input=truncated,
        )
        return response.data[0].embedding


class AnthropicClient(AIClient):
    def __init__(self) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def _do_complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=settings.anthropic_chat_model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    async def embed(self, text: str) -> List[float]:
        fallback = OpenAIClient()
        return await fallback.embed(text)


class GeminiClient(AIClient):
    """Google Gemini via the OpenAI-compatible API endpoint."""

    def __init__(self) -> None:
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_chat_model
        self._base_url = "https://generativelanguage.googleapis.com/v1beta/openai"

    async def _do_complete(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def embed(self, text: str) -> List[float]:
        truncated = text[:8000]
        # gemini-embedding-001 returns 3072 dims natively; use Matryoshka
        # truncation via the OpenAI-compat `dimensions` parameter so output
        # matches the pgvector(768) column without zero-padding corruption.
        payload = {
            "model": settings.gemini_embed_model,
            "input": truncated,
            "dimensions": 768,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        return response.json()["data"][0]["embedding"]


class OllamaClient(AIClient):
    """Local model via Ollama API."""

    # nomic-embed-text produces 768-dim vectors; store the native dimension
    # so cosine similarity is meaningful (no zero-padding corruption).
    _EMBED_DIM = 768

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.chat_model = settings.ollama_chat_model
        self.embed_model = settings.ollama_embed_model

    async def _do_complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
        return response.json()["message"]["content"]

    async def embed(self, text: str) -> List[float]:
        truncated = text[:8000]
        payload = {
            "model": self.embed_model,
            "input": truncated,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embed",
                json=payload,
            )
            response.raise_for_status()
        # Return the raw vector — no padding. Dimension must match the
        # pgvector column size (768). Truncate only if the model returns more.
        vector: List[float] = response.json()["embeddings"][0]
        if len(vector) > self._EMBED_DIM:
            vector = vector[: self._EMBED_DIM]
        return vector


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

# ── Adaptive provider registry (v0.2.1, v0.3 path reserved) ─────────
# Same dynamic pattern as the capability registries. Adding a new
# in-tree provider is a 1-line register call below. v0.3's
# `discover_ai_provider_entry_points()` will let pip-installed
# packages auto-register their providers without core changes.

AI_PROVIDERS: Dict[str, type] = {}


def register_ai_provider(name: str, cls: type) -> None:
    existing = AI_PROVIDERS.get(name)
    if existing is cls:
        return
    if existing is not None:
        raise ValueError(
            f"ai_provider name conflict: {name!r} already registered as "
            f"{existing.__name__}; refusing to overwrite."
        )
    AI_PROVIDERS[name] = cls
    logger.debug("registered ai_provider: %s → %s", name, cls.__name__)


def discover_ai_provider_entry_points() -> None:
    """v0.3 hook — scan installed packages under the
    `workspaceos.ai_providers` entry-point group. No-op for now.
    Activation in v0.3 is a one-line uncomment at the bottom of this
    file."""
    return None  # ← Phase 3: replace with importlib.metadata scan


def _build_client(provider: str) -> AIClient:
    provider = provider.lower().strip()
    cls = AI_PROVIDERS.get(provider)
    if cls is not None:
        return cls()
    # Fallback to OpenAI for unknown values (legacy behavior).
    logger.warning("Unknown AI provider %r, falling back to openai", provider)
    return OpenAIClient()


# In-tree providers — register at import time so the registry is
# populated when the rest of the app calls _build_client().
register_ai_provider("openai", OpenAIClient)
register_ai_provider("anthropic", AnthropicClient)
register_ai_provider("gemini", GeminiClient)
register_ai_provider("ollama", OllamaClient)

# v0.3 activation: uncomment the next line.
# discover_ai_provider_entry_points()


# Cached singletons
_local_client: Optional[AIClient] = None
_cloud_client: Optional[AIClient] = None


def get_local_client() -> AIClient:
    """Client for privacy-sensitive ops: embeddings, extraction, consolidation."""
    global _local_client
    if _local_client is None:
        _local_client = _build_client(settings.local_ai_provider)
        logger.info("Local AI client: %s", type(_local_client).__name__)
    return _local_client


def get_cloud_client() -> AIClient:
    """Client for quality-sensitive ops: draft writing, blog generation, review."""
    global _cloud_client
    if _cloud_client is None:
        _cloud_client = _build_client(settings.cloud_ai_provider)
        logger.info("Cloud AI client: %s", type(_cloud_client).__name__)
    return _cloud_client


def reset_clients() -> None:
    """Clear cached AI client singletons so they pick up new API keys."""
    global _local_client, _cloud_client
    _local_client = None
    _cloud_client = None
    logger.info("AI client singletons reset — will recreate on next call")


def get_ai_client() -> AIClient:
    """Backward compat — returns the cloud client (used by generation code)."""
    return get_cloud_client()
