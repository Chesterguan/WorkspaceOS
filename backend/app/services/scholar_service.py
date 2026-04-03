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
            headers={"User-Agent": "ProjectScribe/1.0 (mailto:ziyuan9512@gmail.com)"},
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

    # Semantic Scholar returned nothing after retries — fall back to OpenAlex
    logger.info(
        "Semantic Scholar search empty for query '%s', falling back to OpenAlex", query
    )
    papers = await search_openalex(query, limit=limit)
    if papers:
        _search_cache[cache_key] = (time.time(), papers)
    return papers


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


# ---------------------------------------------------------------------------
# Extended integrations: CrossRef BibTeX, OpenAlex, Unpaywall, arXiv
# ---------------------------------------------------------------------------

async def doi_to_bibtex(doi: str) -> str:
    """
    Convert a DOI to a BibTeX entry via CrossRef content negotiation.

    Sends a GET to https://doi.org/{doi} with Accept: text/x-bibliography; style=bibtex.
    CrossRef follows the redirect and returns the raw BibTeX string.
    Returns an empty string on failure.
    """
    import asyncio
    url = f"https://doi.org/{doi}"
    headers = {"Accept": "text/x-bibliography; style=bibtex"}
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # Use a fresh client for this call — doi.org redirects to the publisher,
            # so follow_redirects=True is essential.
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "ProjectScribe/1.0 (mailto:ziyuan9512@gmail.com)"},
            ) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            if resp.status_code == 404:
                logger.debug("doi_to_bibtex: DOI not found: %s", doi)
                return ""
            resp.raise_for_status()
            return resp.text.strip()
        except Exception:
            logger.exception("doi_to_bibtex failed for DOI: %s", doi)
            break
    return ""


async def search_openalex(query: str, limit: int = 10) -> List[dict]:
    """
    Search OpenAlex as a Semantic Scholar fallback (250M papers, generous rate limits).

    Normalises the OpenAlex response to match the PaperResult-compatible dict shape
    used throughout scholar_service (paperId, title, abstract, year, authors list of
    {name}, citationCount, url, externalIds, venue).

    Returns an empty list on error.
    """
    import asyncio
    cache_key = f"openalex:{query}:{limit}"
    now = time.time()
    if cache_key in _search_cache:
        cached_time, cached_result = _search_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            logger.debug("openalex cache hit for query: %s", query)
            return cached_result

    max_retries = 2
    for attempt in range(max_retries):
        try:
            resp = await _get_http_client().get(
                "https://api.openalex.org/works",
                params={
                    "search": query,
                    "per-page": limit,
                    "sort": "cited_by_count:desc",
                    "mailto": "ziyuan9512@gmail.com",  # polite pool — faster responses
                },
            )
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            results: List[dict] = []
            for work in data.get("results", []):
                # Normalise authors
                authorships = work.get("authorships") or []
                authors = []
                for a in authorships:
                    author_name = (a.get("author") or {}).get("display_name", "")
                    if author_name:
                        authors.append({"name": author_name})

                # Normalise externalIds (OpenAlex uses doi as a full URL)
                doi_raw = work.get("doi") or ""
                doi_clean = doi_raw.replace("https://doi.org/", "").strip() or None

                ext_ids: dict = {}
                if doi_clean:
                    ext_ids["DOI"] = doi_clean
                arxiv_id = (work.get("ids") or {}).get("arxiv", "")
                if arxiv_id:
                    ext_ids["ArXiv"] = arxiv_id.replace("https://arxiv.org/abs/", "")

                source = (work.get("primary_location") or {}).get("source") or {}
                results.append({
                    "paperId": work.get("id", ""),
                    "title": work.get("title") or "Untitled",
                    "abstract": work.get("abstract") or "",
                    "year": work.get("publication_year"),
                    "authors": authors,
                    "citationCount": work.get("cited_by_count") or 0,
                    "url": work.get("id") or "",  # OpenAlex canonical URL
                    "externalIds": ext_ids,
                    "venue": source.get("display_name", ""),
                })
            _search_cache[cache_key] = (now, results)
            return results
        except Exception:
            logger.exception("search_openalex failed for query: %s", query)
            break
    return []


async def find_open_access_pdf(doi: str) -> Optional[str]:
    """
    Find a freely available PDF URL for a paper via Unpaywall.

    Returns best_oa_location.url_for_pdf when is_oa=True, else None.
    Unpaywall is free; email parameter is required by their API.
    """
    try:
        resp = await _get_http_client().get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": "ziyuan9512@gmail.com"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not data.get("is_oa"):
            return None
        best_loc = data.get("best_oa_location") or {}
        return best_loc.get("url_for_pdf") or None
    except Exception:
        logger.exception("find_open_access_pdf failed for DOI: %s", doi)
    return None


async def search_arxiv(query: str, max_results: int = 5) -> List[dict]:
    """
    Search arXiv for preprints using the Atom API.

    Parses the Atom XML response with stdlib string parsing (no feedparser dependency).
    Returns a list of dicts with keys: title, authors, abstract, pdf_url, arxiv_id, year.
    """
    import re as _re
    try:
        resp = await _get_http_client().get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": query,
                "max_results": max_results,
                "sortBy": "relevance",
            },
        )
        resp.raise_for_status()
        xml = resp.text

        # Extract each <entry> block
        entries = _re.findall(r"<entry>(.*?)</entry>", xml, _re.DOTALL)

        def _text(tag: str, block: str) -> str:
            """Extract first tag value from an XML block via regex."""
            m = _re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, _re.DOTALL)
            return m.group(1).strip() if m else ""

        results: List[dict] = []
        for entry in entries:
            title = _re.sub(r"\s+", " ", _text("title", entry)).strip()
            abstract = _re.sub(r"\s+", " ", _text("summary", entry)).strip()

            # Authors — multiple <author><name>...</name></author> blocks
            author_names: List[str] = []
            for a_block in _re.findall(r"<author>(.*?)</author>", entry, _re.DOTALL):
                name = _text("name", a_block)
                if name:
                    author_names.append(name)

            # arxiv ID from <id>http://arxiv.org/abs/XXXX.XXXXX</id>
            raw_id = _text("id", entry)
            arxiv_id = raw_id.split("/abs/")[-1].strip() if "/abs/" in raw_id else raw_id

            # PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""

            # Year from <published>2023-01-15T...</published>
            published = _text("published", entry)
            year: Optional[int] = None
            if published:
                year_match = _re.match(r"(\d{4})", published)
                if year_match:
                    year = int(year_match.group(1))

            results.append({
                "title": title,
                "authors": author_names,
                "abstract": abstract,
                "pdf_url": pdf_url,
                "arxiv_id": arxiv_id,
                "year": year,
            })
        return results
    except Exception:
        logger.exception("search_arxiv failed for query: %s", query)
    return []


async def generate_bibtex_for_papers(papers: List[dict]) -> str:
    """
    Generate BibTeX entries for a list of papers.

    For papers that have a DOI in externalIds, fetches real BibTeX via CrossRef.
    For papers without a DOI (or when CrossRef fails), synthesises a minimal @misc
    entry from available metadata so the function always returns something for
    non-empty input.
    Returns a single concatenated .bib string ready to write to a file.
    """
    import asyncio
    import re as _re

    logger.info(
        "generate_bibtex_for_papers: processing %d papers (%d with DOI, %d without)",
        len(papers),
        sum(1 for p in papers if _get_doi(p)),
        sum(1 for p in papers if not _get_doi(p)),
    )

    bib_entries: List[str] = []
    # Process DOI-based lookups concurrently to avoid overwhelming CrossRef
    doi_papers = [(i, p) for i, p in enumerate(papers) if _get_doi(p)]
    no_doi_papers = [(i, p) for i, p in enumerate(papers) if not _get_doi(p)]

    async def _fetch_doi_bib(idx: int, paper: dict) -> tuple:
        doi = _get_doi(paper)
        bib = await doi_to_bibtex(doi)  # type: ignore[arg-type]
        return idx, bib, paper

    tasks = [_fetch_doi_bib(i, p) for i, p in doi_papers]
    doi_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build a lookup: index -> bibtex string
    bib_by_index: dict = {}
    for result in doi_results:
        if isinstance(result, Exception):
            logger.warning("generate_bibtex_for_papers: DOI lookup raised exception: %s", result)
            continue
        idx, bib, paper = result
        if bib:
            bib_by_index[idx] = bib
            logger.debug(
                "generate_bibtex_for_papers: CrossRef entry fetched for paper index %d", idx
            )
        else:
            # CrossRef returned nothing — fall back to synthetic entry
            logger.debug(
                "generate_bibtex_for_papers: CrossRef returned empty for paper index %d "
                "(DOI: %s), falling back to synthetic entry",
                idx,
                _get_doi(paper),
            )
            no_doi_papers.append((idx, paper))

    # Generate synthetic entries for papers without DOI or failed CrossRef lookups.
    # Use @misc so the entry is valid for any source type (preprint, conference, journal).
    for idx, paper in no_doi_papers:
        authors = _get_author_names(paper)
        year = paper.get("year") or "n.d."
        title = (paper.get("title") or "Untitled").strip()
        venue = paper.get("venue") or ""

        # Build a cite key: FirstAuthorLastName + Year + first significant title word
        first_author_last = "Unknown"
        if authors:
            parts = authors[0].split()
            first_author_last = _re.sub(r"[^A-Za-z]", "", parts[-1]) if parts else "Unknown"
        title_word = ""
        for w in title.split():
            clean = _re.sub(r"[^A-Za-z]", "", w)
            if len(clean) > 3:
                title_word = clean[:10]
                break
        cite_key = f"{first_author_last}{year}{title_word}" if title_word else f"{first_author_last}{year}"

        author_str = " and ".join(authors) if authors else "Unknown"

        url = paper.get("url") or ""
        ext_ids = paper.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        doi = _get_doi(paper) or ""

        # Build optional extra fields
        extra_lines = ""
        if doi:
            extra_lines += f"  doi = {{{doi}}},\n"
        if arxiv_id:
            extra_lines += f"  note = {{arXiv:{arxiv_id}}},\n"
        elif url:
            extra_lines += f"  url = {{{url}}},\n"
        if venue:
            extra_lines += f"  howpublished = {{{venue}}},\n"

        synthetic = (
            f"@misc{{{cite_key},\n"
            f"  author = {{{author_str}}},\n"
            f"  title = {{{{{title}}}}},\n"
            f"  year = {{{year}}},\n"
            + extra_lines
            + "}"
        )
        logger.debug(
            "generate_bibtex_for_papers: synthetic @misc entry created for paper index %d "
            "(title: %.60s)",
            idx,
            title,
        )
        bib_by_index[idx] = synthetic

    logger.info(
        "generate_bibtex_for_papers: assembled %d BibTeX entries out of %d papers",
        len(bib_by_index),
        len(papers),
    )

    # Assemble in original order
    for i in range(len(papers)):
        if i in bib_by_index:
            bib_entries.append(bib_by_index[i])

    return "\n\n".join(bib_entries)


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
