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
    async def complete(self, system: str, user: str) -> str:
        ...

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        ...


class OpenAIClient(AIClient):
    def __init__(self) -> None:
        import openai
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, system: str, user: str) -> str:
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

    async def complete(self, system: str, user: str) -> str:
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

    async def complete(self, system: str, user: str) -> str:
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
        payload = {
            "model": settings.gemini_embed_model,
            "input": truncated,
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
        data = response.json()["data"][0]["embedding"]
        # Gemini text-embedding-004 returns 768 dims, pad to 1536
        if len(data) < 1536:
            data = data + [0.0] * (1536 - len(data))
        return data


class OllamaClient(AIClient):
    """Local model via Ollama API."""

    _EMBED_DIM = 1536

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.chat_model = settings.ollama_chat_model
        self.embed_model = settings.ollama_embed_model

    async def complete(self, system: str, user: str) -> str:
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
        vector: List[float] = response.json()["embeddings"][0]
        if len(vector) < self._EMBED_DIM:
            vector = vector + [0.0] * (self._EMBED_DIM - len(vector))
        elif len(vector) > self._EMBED_DIM:
            vector = vector[:self._EMBED_DIM]
        return vector


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def _build_client(provider: str) -> AIClient:
    provider = provider.lower().strip()
    if provider == "ollama":
        return OllamaClient()
    elif provider == "gemini":
        return GeminiClient()
    elif provider == "anthropic":
        return AnthropicClient()
    else:
        return OpenAIClient()


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


def get_ai_client() -> AIClient:
    """Backward compat — returns the cloud client (used by generation code)."""
    return get_cloud_client()
