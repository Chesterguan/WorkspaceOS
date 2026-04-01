"""
Semantic Scholar API integration for academic literature search.

Free public API — no key required for basic usage (100 requests/second).
Documentation: https://api.semanticscholar.org/graph/v1
"""
import logging
import time
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"

# Default fields to request for papers — balances completeness with response size
_DEFAULT_FIELDS = "title,abstract,year,authors,citationCount,url,externalIds,venue,publicationTypes"

# ---------------------------------------------------------------------------
# Reused HTTP client (same pattern as repo_context.py)
# ---------------------------------------------------------------------------

_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        # Semantic Scholar can be slow on first request; generous timeout
        _http_client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "ProjectScribe/1.0 (AI PR Secretary; mailto:ziyuan9512@gmail.com)"},
        )
    return _http_client


# ---------------------------------------------------------------------------
# In-process TTL cache to avoid redundant API calls within a session
# ---------------------------------------------------------------------------

_search_cache: Dict[str, Tuple[float, List[dict]]] = {}
_CACHE_TTL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Core API calls
# ---------------------------------------------------------------------------

async def search_papers(
    query: str,
    limit: int = 10,
    fields: str = _DEFAULT_FIELDS,
) -> List[dict]:
    """
    Search Semantic Scholar for papers matching the query string.

    Returns a list of paper dicts. Each paper includes: paperId, title, abstract,
    year, authors (list of name strings), citationCount, url, externalIds, venue.
    Returns an empty list on error.
    """
    cache_key = f"search:{query}:{limit}"
    now = time.time()
    if cache_key in _search_cache:
        cached_time, cached_result = _search_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            logger.debug("scholar_service cache hit for query: %s", query)
            return cached_result

    import asyncio
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = await _get_http_client().get(
                f"{SCHOLAR_API}/paper/search",
                params={"query": query, "limit": limit, "fields": fields},
            )
            if resp.status_code == 429:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning("Semantic Scholar rate limited (429), retrying in %ds...", wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            papers: List[dict] = data.get("data", [])
            _search_cache[cache_key] = (now, papers)
            return papers
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Semantic Scholar search returned HTTP %s for query '%s'",
                exc.response.status_code, query,
            )
            break
        except Exception:
            logger.exception("Semantic Scholar search failed for query: %s", query)
            break
    return []


async def get_paper(paper_id: str) -> Optional[dict]:
    """
    Fetch detailed paper info by Semantic Scholar paper ID or DOI.

    paper_id may be:
      - A Semantic Scholar ID (alphanumeric string)
      - DOI prefixed: "DOI:10.1234/..."
      - ArXiv ID prefixed: "ARXIV:2103.01234"

    Returns None on error or not found.
    """
    fields = (
        "title,abstract,year,authors,citationCount,url,externalIds,"
        "venue,references,citations,publicationTypes"
    )
    try:
        resp = await _get_http_client().get(
            f"{SCHOLAR_API}/paper/{paper_id}",
            params={"fields": fields},
        )
        if resp.status_code == 404:
            logger.debug("Paper not found: %s", paper_id)
            return None
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Semantic Scholar get_paper returned HTTP %s for id '%s'",
            exc.response.status_code,
            paper_id,
        )
    except Exception:
        logger.exception("Semantic Scholar get_paper failed for id: %s", paper_id)
    return None


async def get_citations(paper_id: str, limit: int = 20) -> List[dict]:
    """
    Get papers that cite the given paper.

    Returns a list of paper dicts (the citing papers). Empty list on error.
    """
    fields = "title,abstract,year,authors,citationCount,url,externalIds"
    try:
        resp = await _get_http_client().get(
            f"{SCHOLAR_API}/paper/{paper_id}/citations",
            params={"fields": fields, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        # Response shape: {"data": [{"citingPaper": {...}}, ...]}
        citing: List[dict] = [
            item["citingPaper"]
            for item in data.get("data", [])
            if item.get("citingPaper")
        ]
        return citing
    except Exception:
        logger.exception("get_citations failed for paper_id: %s", paper_id)
    return []


async def get_references(paper_id: str, limit: int = 20) -> List[dict]:
    """
    Get papers referenced by the given paper.

    Returns a list of paper dicts (the referenced papers). Empty list on error.
    """
    fields = "title,abstract,year,authors,citationCount,url,externalIds"
    try:
        resp = await _get_http_client().get(
            f"{SCHOLAR_API}/paper/{paper_id}/references",
            params={"fields": fields, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        # Response shape: {"data": [{"citedPaper": {...}}, ...]}
        cited: List[dict] = [
            item["citedPaper"]
            for item in data.get("data", [])
            if item.get("citedPaper")
        ]
        return cited
    except Exception:
        logger.exception("get_references failed for paper_id: %s", paper_id)
    return []


async def find_related_work(
    project_keywords: List[str],
    limit: int = 15,
) -> List[dict]:
    """
    Search for related work based on a list of project keywords.

    Searches multiple keyword combinations, deduplicates by paperId, and sorts
    by citation count (most-cited first) to surface the most influential work.
    Returns up to `limit` deduplicated papers.
    """
    if not project_keywords:
        return []

    # Build a set of query strings: individual keywords + combined pairs
    queries: List[str] = []
    # Use the most descriptive keywords (first 3) individually
    for kw in project_keywords[:3]:
        if kw.strip():
            queries.append(kw.strip())
    # Also try a combined query with the top 2 keywords for precision
    if len(project_keywords) >= 2:
        combined = " ".join(project_keywords[:2])
        if combined not in queries:
            queries.append(combined)

    seen_ids: set = set()
    all_papers: List[dict] = []

    for query in queries:
        results = await search_papers(query, limit=10)
        for paper in results:
            pid = paper.get("paperId", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(paper)

    # Sort by citation count descending — most influential papers first
    all_papers.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)

    return all_papers[:limit]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _get_author_names(paper: dict) -> List[str]:
    """Extract a clean list of author name strings from a paper dict."""
    authors_raw = paper.get("authors") or []
    names: List[str] = []
    for author in authors_raw:
        if isinstance(author, dict):
            name = author.get("name", "")
            if name:
                names.append(name)
        elif isinstance(author, str):
            names.append(author)
    return names


def _get_doi(paper: dict) -> Optional[str]:
    """Extract DOI from externalIds if available."""
    ext_ids = paper.get("externalIds") or {}
    return ext_ids.get("DOI")


def format_paper_citation(paper: dict) -> str:
    """
    Format a paper as a concise academic citation string.

    Format: Author1, Author2, ... (Year). Title. Venue. DOI: <doi>.
    Gracefully handles missing fields.
    """
    authors = _get_author_names(paper)
    year = paper.get("year")
    title = (paper.get("title") or "Untitled").strip().rstrip(".")
    venue = paper.get("venue") or ""
    doi = _get_doi(paper)
    url = paper.get("url") or ""

    # Format author list: "Smith, J., Jones, A., & Brown, C."
    if authors:
        if len(authors) > 3:
            author_str = f"{authors[0]} et al."
        elif len(authors) == 1:
            author_str = authors[0]
        else:
            author_str = ", ".join(authors[:-1]) + f", & {authors[-1]}"
    else:
        author_str = "Unknown Authors"

    year_str = f" ({year})." if year else "."
    parts = [f"{author_str}{year_str} {title}."]
    if venue:
        parts.append(f" {venue}.")
    if doi:
        parts.append(f" DOI: {doi}")
    elif url:
        parts.append(f" {url}")

    return "".join(parts).strip()


def format_papers_for_prompt(papers: List[dict]) -> str:
    """
    Format a list of papers as a numbered reference context block for AI prompts.

    Each paper is formatted as:
      [N] Authors (Year). Title. Citations: X.
          Abstract: first 200 chars...

    The AI should cite papers using [N] notation.
    Returns an empty string if papers list is empty.
    """
    if not papers:
        return ""

    lines: List[str] = ["## Available Literature (cite using [N] notation)\n"]

    for i, paper in enumerate(papers, start=1):
        authors = _get_author_names(paper)
        year = paper.get("year", "n.d.")
        title = (paper.get("title") or "Untitled").strip()
        citation_count = paper.get("citationCount") or 0
        abstract = paper.get("abstract") or ""
        doi = _get_doi(paper)
        url = paper.get("url") or ""

        # Author shorthand
        if authors:
            author_str = authors[0] + (" et al." if len(authors) > 1 else "")
        else:
            author_str = "Unknown"

        ref_line = f"[{i}] {author_str} ({year}). {title}. Citations: {citation_count}."
        if doi:
            ref_line += f" DOI: {doi}"
        elif url:
            ref_line += f" URL: {url}"

        lines.append(ref_line)

        if abstract:
            excerpt = abstract[:200].strip()
            if len(abstract) > 200:
                excerpt += "..."
            lines.append(f"    Abstract: {excerpt}")

        lines.append("")  # blank line between entries

    return "\n".join(lines)
