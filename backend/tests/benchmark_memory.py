"""
Benchmark memory retrieval quality.

Measures: precision@5, MRR, latency per query.
Compares: baseline (cosine only) vs upgraded (hybrid + rerank).

Usage:
    python -m tests.benchmark_memory baseline
    python -m tests.benchmark_memory upgraded
    python -m tests.benchmark_memory compare
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

# Add backend root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.memory import MemoryEntry
from app.models.project import Project

QUERIES_FILE = Path(__file__).parent / "test_queries.json"
RESULTS_DIR = Path(__file__).parent
BASELINE_FILE = RESULTS_DIR / "baseline_results.json"
UPGRADED_FILE = RESULTS_DIR / "upgraded_results.json"


def load_test_queries() -> List[Dict[str, Any]]:
    with open(QUERIES_FILE) as f:
        return json.load(f)


async def get_project_map(db: AsyncSession) -> Dict[str, str]:
    """Map project names to IDs."""
    result = await db.execute(select(Project))
    projects = result.scalars().all()
    return {p.name: str(p.id) for p in projects}


def score_results(
    entries: List[Any],
    expected_keywords: List[str],
) -> Dict[str, float]:
    """Score search results against expected keywords."""
    if not entries:
        return {"precision": 0.0, "mrr": 0.0, "hits": 0}

    # Combine all result content
    all_content = " ".join(e.content.lower() for e in entries)
    hits = sum(
        1 for kw in expected_keywords if kw.lower() in all_content
    )
    precision = hits / len(expected_keywords) if expected_keywords else 0.0

    # MRR: rank of first result containing any expected keyword
    mrr = 0.0
    for rank, entry in enumerate(entries, 1):
        content_lower = entry.content.lower()
        if any(kw.lower() in content_lower for kw in expected_keywords):
            mrr = 1.0 / rank
            break

    return {"precision": precision, "mrr": mrr, "hits": hits}


async def run_benchmark(
    search_fn: Callable,
    test_queries: List[Dict[str, Any]],
    db: AsyncSession,
    project_map: Dict[str, str],
    label: str = "benchmark",
) -> Dict[str, Any]:
    """Run benchmark against a search function."""
    results = []

    for q in test_queries:
        # Resolve project_id
        project_name = q.get("project")
        project_id = None
        if project_name and project_name in project_map:
            import uuid
            project_id = uuid.UUID(project_map[project_name])
        elif project_map:
            # Use first available project for null-project queries
            import uuid
            project_id = uuid.UUID(list(project_map.values())[0])

        if project_id is None:
            results.append({
                "query": q["query"],
                "precision": 0.0,
                "mrr": 0.0,
                "latency_ms": 0.0,
                "results_count": 0,
                "skipped": True,
            })
            continue

        start = time.perf_counter()
        try:
            entries = await search_fn(
                project_id=project_id,
                query=q["query"],
                limit=5,
                db=db,
            )
        except Exception as e:
            print(f"  [WARN] Query '{q['query']}' failed: {e}")
            entries = []
        latency = (time.perf_counter() - start) * 1000

        scores = score_results(entries, q["expected_keywords"])
        results.append({
            "query": q["query"],
            "precision": scores["precision"],
            "mrr": scores["mrr"],
            "latency_ms": round(latency, 2),
            "results_count": len(entries),
            "hits": scores["hits"],
            "expected_keywords": q["expected_keywords"],
        })

    # Aggregate
    valid = [r for r in results if not r.get("skipped")]
    n = len(valid) or 1
    summary = {
        "label": label,
        "total_queries": len(test_queries),
        "evaluated_queries": len(valid),
        "avg_precision": round(sum(r["precision"] for r in valid) / n, 4),
        "avg_mrr": round(sum(r["mrr"] for r in valid) / n, 4),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in valid) / n, 2),
        "details": results,
    }
    return summary


def compare_results() -> str:
    """Compare baseline vs upgraded results."""
    if not BASELINE_FILE.exists():
        return "No baseline results found. Run: python -m tests.benchmark_memory baseline"
    if not UPGRADED_FILE.exists():
        return "No upgraded results found. Run: python -m tests.benchmark_memory upgraded"

    with open(BASELINE_FILE) as f:
        baseline = json.load(f)
    with open(UPGRADED_FILE) as f:
        upgraded = json.load(f)

    lines = [
        "=" * 60,
        "MEMORY SEARCH BENCHMARK COMPARISON",
        "=" * 60,
        "",
        f"{'Metric':<25} {'Baseline':>12} {'Upgraded':>12} {'Delta':>12}",
        "-" * 60,
    ]

    for metric in ["avg_precision", "avg_mrr", "avg_latency_ms"]:
        b = baseline.get(metric, 0)
        u = upgraded.get(metric, 0)
        delta = u - b
        sign = "+" if delta >= 0 else ""
        # For latency, lower is better
        indicator = ""
        if metric == "avg_latency_ms":
            indicator = " (slower)" if delta > 0 else " (faster)"
        else:
            indicator = " (better)" if delta > 0 else " (worse)" if delta < 0 else ""

        lines.append(
            f"{metric:<25} {b:>12.4f} {u:>12.4f} {sign}{delta:>10.4f}{indicator}"
        )

    lines.append("-" * 60)
    lines.append("")

    # Per-query comparison
    lines.append("Per-query precision changes:")
    base_details = {d["query"]: d for d in baseline.get("details", [])}
    for d in upgraded.get("details", []):
        bd = base_details.get(d["query"], {})
        bp = bd.get("precision", 0)
        up = d.get("precision", 0)
        if up != bp:
            lines.append(f"  {d['query'][:50]:<50} {bp:.2f} -> {up:.2f}")

    report = "\n".join(lines)
    print(report)

    # Save report
    report_file = RESULTS_DIR / "benchmark_comparison.txt"
    with open(report_file, "w") as f:
        f.write(report)
    print(f"\nReport saved to {report_file}")
    return report


async def main(mode: str) -> None:
    from app.services import memory_service

    test_queries = load_test_queries()

    async with AsyncSessionLocal() as db:
        project_map = await get_project_map(db)

        if not project_map:
            print("No projects found in database. Benchmark requires data.")
            return

        print(f"Found {len(project_map)} projects: {list(project_map.keys())}")

        if mode == "baseline":
            print("\nRunning BASELINE benchmark (cosine-only search)...")
            results = await run_benchmark(
                search_fn=memory_service.search_memory_vector,
                test_queries=test_queries,
                db=db,
                project_map=project_map,
                label="baseline_cosine_only",
            )
            with open(BASELINE_FILE, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Baseline: precision={results['avg_precision']:.4f}, "
                  f"MRR={results['avg_mrr']:.4f}, "
                  f"latency={results['avg_latency_ms']:.2f}ms")
            print(f"Saved to {BASELINE_FILE}")

        elif mode == "upgraded":
            print("\nRunning UPGRADED benchmark (hybrid + rerank)...")
            results = await run_benchmark(
                search_fn=memory_service.search_memory,
                test_queries=test_queries,
                db=db,
                project_map=project_map,
                label="upgraded_hybrid_rerank",
            )
            with open(UPGRADED_FILE, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Upgraded: precision={results['avg_precision']:.4f}, "
                  f"MRR={results['avg_mrr']:.4f}, "
                  f"latency={results['avg_latency_ms']:.2f}ms")
            print(f"Saved to {UPGRADED_FILE}")

        elif mode == "compare":
            pass  # Handled below

    if mode == "compare":
        compare_results()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if mode not in ("baseline", "upgraded", "compare"):
        print(f"Usage: python -m tests.benchmark_memory [baseline|upgraded|compare]")
        sys.exit(1)

    if mode == "compare":
        compare_results()
    else:
        asyncio.run(main(mode))
