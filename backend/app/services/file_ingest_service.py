"""
File ingest service: extract text from uploaded files/URLs, auto-tag via AI,
and store as memory entries with enriched metadata.

Pipeline:
  File/URL → extract text → AI auto-tag → memory_service.add_entry() → set metadata_ → return
"""
import logging
import re
import uuid
from typing import Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.services.agents import extract_json
from app.services.ai_client import get_cloud_client
from app.services.memory_service import add_entry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_CONTENT_CHARS = 50000   # max chars extracted from a file
MAX_MEMORY_CHARS = 10000    # max chars stored in the memory entry content
MAX_URL_BYTES = 5 * 1024 * 1024  # 5 MB max download for URL imports


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
async def extract_text(content_bytes: bytes, mime_type: str) -> str:
    """Extract readable text from file bytes based on MIME type.

    Supports PDF (PyPDF2), HTML (strip tags), and text-based formats
    (markdown, plain text, source code). Truncates to MAX_CONTENT_CHARS.
    """
    text = ""

    if mime_type == "application/pdf":
        try:
            import io
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(content_bytes))
            pages = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
            text = "\n\n".join(pages)
        except Exception:
            logger.warning("PDF extraction failed; storing empty text")
            text = ""

    elif "html" in mime_type:
        # Strip HTML tags to get plain text
        try:
            decoded = content_bytes.decode("utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", " ", decoded)
            text = re.sub(r"\s+", " ", text).strip()
        except Exception:
            text = ""

    else:
        # text/plain, text/markdown, application/json, source code, etc.
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = ""

    return text[:MAX_CONTENT_CHARS]


# ---------------------------------------------------------------------------
# AI auto-tagging
# ---------------------------------------------------------------------------
async def auto_tag(filename: str, text_preview: str, mime_type: str) -> Dict:
    """Use cloud AI to generate 3-5 tags and a one-line summary.

    Returns {"tags": [...], "summary": "..."}.
    Falls back to {"tags": [], "summary": filename} on failure.
    """
    fallback = {"tags": [], "summary": filename}
    try:
        ai = get_cloud_client()
        system = (
            "You are a document classifier. Given a filename, MIME type, and text preview, "
            "return a JSON object with exactly two keys:\n"
            '  "tags": an array of 3-5 short lowercase tags describing the content\n'
            '  "summary": a single sentence summarizing the document\n'
            "Output ONLY valid JSON, no markdown fences, no extra text."
        )
        user = (
            f"Filename: {filename}\n"
            f"MIME type: {mime_type}\n"
            f"Preview (first 2000 chars):\n{text_preview[:2000]}"
        )
        raw = await ai.complete(system, user)
        result = extract_json(raw)
        if result and "tags" in result and "summary" in result:
            return result
        return fallback
    except Exception:
        logger.debug("auto_tag failed for %s; using fallback", filename)
        return fallback


# ---------------------------------------------------------------------------
# Main ingest pipeline
# ---------------------------------------------------------------------------
async def ingest_file(
    project_id: uuid.UUID,
    filename: str,
    content_bytes: bytes,
    source: str,
    mime_type: str,
    user_tags: Optional[List[str]],
    db: AsyncSession,
    url: Optional[str] = None,
) -> MemoryEntry:
    """Ingest a file into the memory system with AI-generated metadata.

    Pipeline: extract text -> auto-tag -> merge tags -> add_entry -> set metadata_.
    """
    # 1. Extract text
    text = await extract_text(content_bytes, mime_type)

    # 2. Auto-tag via AI
    tag_result = await auto_tag(filename, text, mime_type)

    # 3. Merge user tags with AI tags (deduplicate, preserve order)
    ai_tags: List[str] = tag_result.get("tags", [])
    merged_tags: List[str] = list(ai_tags)
    if user_tags:
        for t in user_tags:
            if t.lower() not in [x.lower() for x in merged_tags]:
                merged_tags.append(t)
    summary: str = tag_result.get("summary", filename)

    # 4. Store as memory entry (handles embedding + contextual retrieval)
    entry_type = "url" if source == "url" else "file"
    # Truncate content for memory storage
    memory_content = text[:MAX_MEMORY_CHARS] if text else f"[{mime_type}] {filename}"
    source_ref = url if url else filename

    entry = await add_entry(
        project_id=project_id,
        entry_type=entry_type,
        content=memory_content,
        source_ref=source_ref,
        db=db,
    )

    # 5. Set enriched metadata
    entry.metadata_ = {
        "source": source,
        "filename": filename,
        "mime_type": mime_type,
        "tags": merged_tags,
        "summary": summary,
        "file_size": len(content_bytes),
        "url": url,
    }
    await db.flush()
    await db.refresh(entry)

    return entry


# ---------------------------------------------------------------------------
# URL ingest
# ---------------------------------------------------------------------------
async def ingest_url(
    project_id: uuid.UUID,
    url: str,
    user_tags: Optional[List[str]],
    db: AsyncSession,
) -> MemoryEntry:
    """Fetch a URL and ingest its content as a memory entry.

    Downloads up to MAX_URL_BYTES, detects MIME type from response headers,
    then delegates to ingest_file().
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    content_bytes = response.content
    if len(content_bytes) > MAX_URL_BYTES:
        content_bytes = content_bytes[:MAX_URL_BYTES]

    # Detect MIME type from Content-Type header
    content_type = response.headers.get("content-type", "text/plain")
    mime_type = content_type.split(";")[0].strip()

    # Derive filename from URL path
    from urllib.parse import urlparse
    parsed = urlparse(url)
    filename = parsed.path.split("/")[-1] or "index.html"

    return await ingest_file(
        project_id=project_id,
        filename=filename,
        content_bytes=content_bytes,
        source="url",
        mime_type=mime_type,
        user_tags=user_tags,
        db=db,
        url=url,
    )
