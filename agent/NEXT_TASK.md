# Next Task

## Status
ready

## Task
Execute memory upgrade plan: docs/superpowers/plans/2026-04-02-memory-upgrade.md

Start with Task 1 (benchmark framework + baseline), then Tasks 2-7 sequentially.

## Scope
- Files: [backend/app/services/memory_service.py, backend/app/models/memory.py, backend/app/routers/memory.py, backend/tests/*, frontend/lib/api.ts, frontend/app/projects/[projectId]/memory/page.tsx]
- Tests: [backend/tests/benchmark_memory.py]

## Acceptance Criteria
- [ ] Baseline benchmark recorded (precision@5, latency)
- [ ] Hybrid search (pgvector + BM25 + RRF) implemented
- [ ] FlashRank reranking added
- [ ] Contextual retrieval pre-processing on write
- [ ] Cross-project search endpoint + UI
- [ ] Post-upgrade benchmark shows measurable improvement
- [ ] Comparison report generated

## Priority
high

## Plan File
docs/superpowers/plans/2026-04-02-memory-upgrade.md
