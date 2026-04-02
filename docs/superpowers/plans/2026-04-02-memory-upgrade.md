# Memory System Upgrade: Hybrid RAG with Benchmarks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the memory system from simple pgvector cosine search to a production-grade hybrid RAG pipeline with benchmarks proving improvement.

**Architecture:** PostgreSQL hybrid search (pgvector + full-text BM25) → Reciprocal Rank Fusion → FlashRank reranking → contextual retrieval pre-processing. Add cross-project search. Benchmark before/after with test queries.

**Tech Stack:** pgvector (existing), PostgreSQL tsvector (built-in BM25), FlashRank (4MB Python package), Ollama (contextual chunk descriptions)

---

## Current State (Baseline)

- `memory_service.py`: pgvector cosine similarity only
- No keyword/BM25 search
- No reranking
- No cross-project search
- No contextual pre-processing of stored entries
- 768-dim embeddings via Ollama nomic-embed-text

## Target State

```
Query → [1. BM25 full-text search] ──┐
       → [2. pgvector cosine search] ─┼→ [3. RRF Fusion] → [4. FlashRank Rerank] → Top-K results
                                       │
       Cross-project flag? ────────────┘ (search all projects or just one)
```

Pre-processing on write:
```
New entry → [Ollama: generate context description] → Store: original + context + embedding + tsvector
```

---

## Task 1: Benchmark Framework + Baseline Measurement

**Files:**
- Create: `backend/tests/benchmark_memory.py`
- Create: `backend/tests/test_queries.json`

- [ ] **Step 1: Create test query set**

Create `backend/tests/test_queries.json` with 20 test queries across projects, each with expected relevant entry types and keywords:

```json
[
  {"query": "patient data consent governance", "project": "HAVEN", "expected_keywords": ["consent", "patient", "FHIR", "health asset"]},
  {"query": "data registry schema definition", "project": "PSDL", "expected_keywords": ["schema", "PSDL", "registry", "portable"]},
  {"query": "how to authenticate users", "project": null, "expected_keywords": ["auth", "login", "token", "JWT"]},
  {"query": "recent release changes", "project": "HAVEN", "expected_keywords": ["release", "v2", "changelog"]},
  ...
]
```

- [ ] **Step 2: Create benchmark script**

```python
# backend/tests/benchmark_memory.py
"""
Benchmark memory retrieval quality.
Measures: precision@5, recall@5, MRR, latency per query.
Compares: baseline (cosine only) vs upgraded (hybrid + rerank).
"""

async def run_benchmark(search_fn, test_queries, db):
    results = []
    for q in test_queries:
        start = time.time()
        entries = await search_fn(q["project_id"], q["query"], limit=5, db=db)
        latency = time.time() - start

        # Score: how many expected keywords appear in returned entries
        hits = sum(1 for kw in q["expected_keywords"]
                   if any(kw.lower() in e.content.lower() for e in entries))
        precision = hits / len(q["expected_keywords"])

        results.append({
            "query": q["query"],
            "precision": precision,
            "latency_ms": latency * 1000,
            "results_count": len(entries),
        })

    avg_precision = sum(r["precision"] for r in results) / len(results)
    avg_latency = sum(r["latency_ms"] for r in results) / len(results)
    return {"avg_precision": avg_precision, "avg_latency_ms": avg_latency, "details": results}
```

- [ ] **Step 3: Run baseline benchmark**

Run against current memory_service.search_memory (cosine only). Save results to `backend/tests/baseline_results.json`.

---

## Task 2: Add Full-Text Search (BM25 via tsvector)

**Files:**
- Create: `backend/alembic/versions/0005_memory_fulltext.py`
- Modify: `backend/app/models/memory.py`
- Modify: `backend/app/services/memory_service.py`

- [ ] **Step 1: Add tsvector column + GIN index**

Migration 0005:
```sql
ALTER TABLE memory_entries ADD COLUMN search_vector tsvector;
UPDATE memory_entries SET search_vector = to_tsvector('english', coalesce(content, ''));
CREATE INDEX idx_memory_entries_search_vector ON memory_entries USING gin(search_vector);

-- Trigger to auto-update tsvector on insert/update
CREATE OR REPLACE FUNCTION memory_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := to_tsvector('english', coalesce(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_memory_search_vector
  BEFORE INSERT OR UPDATE OF content ON memory_entries
  FOR EACH ROW EXECUTE FUNCTION memory_search_vector_update();
```

- [ ] **Step 2: Add BM25 search function to memory_service.py**

```python
async def search_memory_bm25(
    project_id: uuid.UUID,
    query: str,
    limit: int,
    db: AsyncSession,
    cross_project: bool = False,
) -> List[MemoryEntry]:
    """Full-text BM25 search using PostgreSQL tsvector."""
    tsquery = func.plainto_tsquery('english', query)
    stmt = (
        select(MemoryEntry)
        .where(MemoryEntry.search_vector.op('@@')(tsquery))
        .order_by(func.ts_rank(MemoryEntry.search_vector, tsquery).desc())
        .limit(limit)
    )
    if not cross_project:
        stmt = stmt.where(MemoryEntry.project_id == project_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())
```

---

## Task 3: Hybrid Search with Reciprocal Rank Fusion

**Files:**
- Modify: `backend/app/services/memory_service.py`

- [ ] **Step 1: Implement RRF fusion**

```python
def reciprocal_rank_fusion(
    ranked_lists: List[List[MemoryEntry]],
    k: int = 60,
) -> List[MemoryEntry]:
    """Fuse multiple ranked result lists using RRF. Returns deduplicated, re-ranked list."""
    scores: Dict[uuid.UUID, float] = {}
    entry_map: Dict[uuid.UUID, MemoryEntry] = {}

    for ranked_list in ranked_lists:
        for rank, entry in enumerate(ranked_list):
            scores[entry.id] = scores.get(entry.id, 0) + 1.0 / (rank + k)
            entry_map[entry.id] = entry

    sorted_ids = sorted(scores.keys(), key=lambda eid: scores[eid], reverse=True)
    return [entry_map[eid] for eid in sorted_ids]
```

- [ ] **Step 2: New hybrid search function**

```python
async def search_memory_hybrid(
    project_id: uuid.UUID,
    query: str,
    limit: int,
    db: AsyncSession,
    cross_project: bool = False,
) -> List[MemoryEntry]:
    """Hybrid search: pgvector cosine + BM25 full-text, fused with RRF."""
    # Run both searches in parallel
    vector_results = await search_memory_vector(project_id, query, limit=limit*2, db=db, cross_project=cross_project)
    bm25_results = await search_memory_bm25(project_id, query, limit=limit*2, db=db, cross_project=cross_project)

    # Fuse
    fused = reciprocal_rank_fusion([vector_results, bm25_results])
    return fused[:limit]
```

- [ ] **Step 3: Update search_memory to use hybrid by default**

Replace the old `search_memory` body with `search_memory_hybrid`, keeping the same signature + adding optional `cross_project` param.

---

## Task 4: FlashRank Reranking

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/services/memory_service.py`

- [ ] **Step 1: Add FlashRank dependency**

Add to requirements.txt: `flashrank>=0.2.0`

- [ ] **Step 2: Add reranking function**

```python
_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from flashrank import Ranker
        _reranker = Ranker(model_name="ms-marco-MiniLM-L-6-v2")
    return _reranker

async def rerank_results(
    query: str,
    entries: List[MemoryEntry],
    top_k: int = 5,
) -> List[MemoryEntry]:
    """Rerank memory entries using FlashRank cross-encoder."""
    if not entries:
        return entries

    import asyncio
    reranker = _get_reranker()

    passages = [{"id": str(e.id), "text": e.content} for e in entries]
    loop = asyncio.get_running_loop()
    reranked = await loop.run_in_executor(None, reranker.rerank, query, passages)

    entry_map = {str(e.id): e for e in entries}
    return [entry_map[r["id"]] for r in reranked[:top_k] if r["id"] in entry_map]
```

- [ ] **Step 3: Wire reranking into hybrid search**

```python
async def search_memory_hybrid(
    project_id, query, limit, db, cross_project=False, rerank=True,
):
    vector_results = await search_memory_vector(...)
    bm25_results = await search_memory_bm25(...)
    fused = reciprocal_rank_fusion([vector_results, bm25_results])

    if rerank and len(fused) > limit:
        return await rerank_results(query, fused[:limit*3], top_k=limit)
    return fused[:limit]
```

---

## Task 5: Contextual Retrieval (Pre-processing on Write)

**Files:**
- Modify: `backend/app/services/memory_service.py`

- [ ] **Step 1: Add context generation on entry creation**

```python
async def _generate_context_description(content: str, entry_type: str) -> str:
    """Use local AI to generate a context description for the entry.
    Prepended to the content before embedding for better semantic matching."""
    local_ai = get_local_client()
    try:
        ctx = await local_ai.complete(
            "Generate a 1-2 sentence context description for this text that explains "
            "what it is, why it matters, and what concepts it relates to. Be specific.",
            f"[{entry_type}] {content[:1000]}",
        )
        return ctx.strip()
    except Exception:
        return ""

async def add_entry(project_id, entry_type, content, source_ref, db):
    # Generate context description
    context = await _generate_context_description(content, entry_type)

    # Embed the content WITH context for better semantic matching
    embed_text = f"{context}\n\n{content}" if context else content
    embedding = await ai.embed(embed_text)

    entry = MemoryEntry(
        project_id=project_id,
        entry_type=entry_type,
        content=content,  # store original content (not with context)
        source_ref=source_ref,
        embedding=embedding,
        # context stored in a new field or prepended to content
    )
```

---

## Task 6: Cross-Project Search

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/routers/memory.py`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/projects/[projectId]/memory/page.tsx`

- [ ] **Step 1: Add cross-project search endpoint**

```python
# In memory router:
POST /memory/search-all
Body: {"query": str, "limit": int}
# Searches across ALL projects, returns results with project_id + project_name
```

- [ ] **Step 2: Add global memory search page or section**

In the portfolio page or a new /memory page, add a search bar that searches across all projects. Results show which project each entry belongs to.

---

## Task 7: Run Post-Upgrade Benchmark + Compare

- [ ] **Step 1: Run the same 20 test queries against the new hybrid search**
- [ ] **Step 2: Compare baseline vs upgraded: precision@5, MRR, latency**
- [ ] **Step 3: Generate a comparison report**

Expected improvements:
- Precision: +20-40% (hybrid catches keyword matches vector misses)
- MRR: +15-30% (reranking pushes truly relevant results to top)
- Latency: +50-100ms (acceptable for the quality gain)

---

## Task 8: Commit + Document

- [ ] Commit all changes
- [ ] Update CLAUDE.md with new memory architecture
- [ ] Update agent/DECISIONS.md
- [ ] Update project memory
