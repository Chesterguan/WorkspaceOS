"""OT-2 protocol catalog ingest source.

Walks a configured directory (mounted inside the backend container) of
Python files, parses each as an Opentrons OT-2 protocol using Python's
`ast` module (no exec of untrusted code), and creates one `protocol`
knowledge node per file.

Files are filtered to:
  - `.py` extension only
  - Must contain an `import opentrons` or `from opentrons` line
  - Must define a `run(` function at module level

The external_id is `ot2:<sha256 of the absolute path string>` — stable
across ticks as long as the file stays at the same path.

Re-ingest on change: the external_id encodes the path only (not mtime),
so when a file's content changes the existing node is updated in-place
via `update_node_content()`.  New files get a fresh node via the
standard `upsert_node()` path.

Config (all optional):
    watch_path:             Path inside the container. Default /protocols.
                            Users can bind-mount their protocol library here.
    recursive:              Walk subdirectories. Default true.
    max_files_per_tick:     Safety cap. Default 100.
    poll_interval_seconds:  How often to scan. Default 1800 (30 min).
"""
from __future__ import annotations

import ast
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select

from app.capabilities.base import IngestContext, IngestSource
from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeNode

logger = logging.getLogger(__name__)

# Directories that never hold meaningful protocol files.
_SKIP_DIR_NAMES = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv", "node_modules", "dist", "build",
})


class OT2ProtocolsIngest(IngestSource):
    """Catalogs OT-2 Python protocols from a watch directory."""

    label = "ot2-protocols"
    default_poll_interval_seconds = 1800

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        watch_path: str = config.get("watch_path") or "/protocols"
        recursive: bool = bool(config.get("recursive", True))
        max_files_per_tick: int = int(config.get("max_files_per_tick") or 100)

        root = Path(watch_path)
        if not root.exists() or not root.is_dir():
            logger.debug("ot2-protocols: watch_path %s does not exist; skipping", watch_path)
            return 0

        ingested = 0
        updated = 0
        candidates = self._walk_py_files(root, recursive)

        for path in candidates:
            if ingested + updated >= max_files_per_tick:
                ctx.log(
                    "warn",
                    f"ot2-protocols: hit per-tick cap of {max_files_per_tick}; "
                    "remaining files will be processed next tick",
                )
                break

            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("ot2-protocols: cannot read %s — %s", path, exc)
                continue

            # Cheap text heuristic before paying the cost of ast.parse.
            if not _looks_like_ot2(source):
                continue

            try:
                parsed = ast.parse(source, filename=str(path))
            except SyntaxError as exc:
                logger.debug("ot2-protocols: skip %s — SyntaxError: %s", path, exc)
                continue

            if not _has_run_function(parsed):
                continue

            meta_dict = _extract_metadata(parsed)
            req_dict = _extract_requirements(parsed)
            labware = _extract_load_calls(parsed, "load_labware")
            modules = _extract_load_calls(parsed, "load_module")
            instruments = _extract_load_calls(parsed, "load_instrument")

            # Prefer metadata apiLevel, fall back to requirements apiLevel.
            api_level = (
                meta_dict.get("apiLevel")
                or req_dict.get("apiLevel")
                or ""
            )

            rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
            title = meta_dict.get("protocolName") or path.name
            content = _build_content(
                meta_dict=meta_dict,
                api_level=api_level,
                rel=rel,
                labware=labware,
                modules=modules,
                instruments=instruments,
                source=source,
            )
            node_metadata = {
                "protocol_name": meta_dict.get("protocolName"),
                "author": meta_dict.get("author"),
                "api_level": api_level or None,
                "robot_type": req_dict.get("robotType"),
                "labware": labware,
                "modules": modules,
                "instruments": instruments,
                "path_relative": rel,
                "path_absolute": path.as_posix(),
            }

            # external_id is path-stable so the same file can be updated
            # across ticks when its content changes.
            external_id = _make_external_id(path)

            try:
                result = await _upsert_or_update_node(
                    ctx=ctx,
                    node_type="protocol",
                    title=title,
                    content=content,
                    external_id=external_id,
                    metadata=node_metadata,
                )
                if result == "inserted":
                    ingested += 1
                    ctx.log("info", f"ot2-protocols: catalogued {rel}",
                            meta={"path": path.as_posix()})
                elif result == "updated":
                    updated += 1
                    ctx.log("info", f"ot2-protocols: updated {rel}",
                            meta={"path": path.as_posix()})
            except Exception as exc:
                logger.warning("ot2-protocols: skip %s — %s", path, exc)
                continue

        total = ingested + updated
        if total:
            ctx.log(
                "success",
                f"ot2-protocols: {ingested} new, {updated} updated this tick",
            )
        else:
            logger.debug("ot2-protocols: no new or changed protocols this tick")
        return ingested  # convention: return count of *new* nodes

    @staticmethod
    def _walk_py_files(root: Path, recursive: bool) -> Iterable[Path]:
        """Yield .py files under root, skipping noisy directories."""
        if recursive:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in _SKIP_DIR_NAMES and not d.startswith(".")
                ]
                for fname in filenames:
                    if fname.endswith(".py") and not fname.startswith("."):
                        yield Path(dirpath) / fname
        else:
            for entry in root.iterdir():
                if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("."):
                    yield entry


# ── AST helpers ─────────────────────────────────────────────────────────────

def _looks_like_ot2(source: str) -> bool:
    """Cheap check before parsing — avoids AST cost on non-OT2 files."""
    return "import opentrons" in source or "from opentrons" in source


def _has_run_function(tree: ast.Module) -> bool:
    """Return True if the module defines a top-level `run` function."""
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
        for node in ast.iter_child_nodes(tree)
    )


def _extract_metadata(tree: ast.Module) -> Dict[str, Any]:
    """Extract the module-level `metadata = {...}` dict if present."""
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "metadata"
            and isinstance(node.value, ast.Dict)
        ):
            return _ast_dict_to_py(node.value)
    return {}


def _extract_requirements(tree: ast.Module) -> Dict[str, Any]:
    """Extract the module-level `requirements = {...}` dict if present."""
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "requirements"
            and isinstance(node.value, ast.Dict)
        ):
            return _ast_dict_to_py(node.value)
    return {}


def _ast_dict_to_py(node: ast.Dict) -> Dict[str, Any]:
    """Convert a simple AST dict (string keys, constant values) to a real dict.

    Only handles string/int/float/bool constants — that covers all known
    OT-2 metadata fields. Complex values are skipped.
    """
    result: Dict[str, Any] = {}
    for key_node, val_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        if isinstance(val_node, ast.Constant):
            result[key_node.value] = val_node.value
    return result


def _extract_load_calls(tree: ast.Module, method_name: str) -> List[str]:
    """Find all `protocol.<method_name>("first-string-arg", ...)` calls in
    the `run` function body and return the first string argument from each.

    Best-effort: skips calls where the first arg isn't a plain string literal.
    """
    results: List[str] = []
    run_body = _find_run_body(tree)
    if run_body is None:
        return results

    for node in ast.walk(run_body):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match: anything.method_name(...)
        if not (isinstance(func, ast.Attribute) and func.attr == method_name):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            results.append(first_arg.value)

    return results


def _find_run_body(tree: ast.Module) -> Optional[ast.AST]:
    """Return the run function node so we can walk inside it."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            return node
    return None


# ── Content + ID helpers ─────────────────────────────────────────────────────

def _build_content(
    *,
    meta_dict: Dict[str, Any],
    api_level: str,
    rel: str,
    labware: List[str],
    modules: List[str],
    instruments: List[str],
    source: str,
) -> str:
    author = meta_dict.get("author") or "—"
    description = meta_dict.get("description") or "—"
    api_display = api_level or "—"

    labware_lines = "\n".join(f"- {lw}" for lw in labware) if labware else "- (none detected)"
    module_lines = "\n".join(f"- {m}" for m in modules) if modules else "- (none detected)"
    instrument_lines = "\n".join(f"- {i}" for i in instruments) if instruments else "- (none detected)"

    # Cap source at 8000 chars as specified.
    source_snippet = source[:8000]

    return (
        f"Author: {author}\n"
        f"API Level: {api_display}\n"
        f"Path: {rel}\n"
        f"\nDescription:\n{description}\n"
        f"\nLabware:\n{labware_lines}\n"
        f"\nModules:\n{module_lines}\n"
        f"\nInstruments:\n{instrument_lines}\n"
        f"\nSource (first 8000 chars):\n```python\n{source_snippet}\n```"
    )


def _make_external_id(path: Path) -> str:
    """Stable external_id based on the absolute path (not mtime/content).

    Using the path alone means the same file across ticks gets the same
    ID, allowing updates when content changes rather than treating each
    version as a new node.
    """
    digest = hashlib.sha256(path.as_posix().encode()).hexdigest()[:16]
    return f"ot2:{digest}"


# ── DB upsert-or-update ──────────────────────────────────────────────────────

async def _upsert_or_update_node(
    *,
    ctx: IngestContext,
    node_type: str,
    title: str,
    content: str,
    external_id: str,
    metadata: Dict[str, Any],
) -> str:
    """Insert a new node or update the existing one if content changed.

    Returns "inserted", "updated", or "unchanged".

    We go to the DB directly here (rather than calling ctx.upsert_node)
    because the base upsert_node is insert-only (returns False on
    duplicate without updating).  This keeps re-ingest correct when a
    protocol file is edited between ticks.
    """
    full_meta = dict(metadata)
    full_meta["external_id"] = external_id
    full_meta["capability_source"] = ctx.source

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(KnowledgeNode).where(
                    KnowledgeNode.user_id == ctx.user_id,
                    KnowledgeNode.metadata_["external_id"].astext == external_id,
                ).limit(1)
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                node = KnowledgeNode(
                    user_id=ctx.user_id,
                    node_type=node_type,
                    title=title[:160],
                    content=content,
                    source_refs=[{
                        "kind": "capability",
                        "source": ctx.source,
                        "external_id": external_id,
                    }],
                    metadata_=full_meta,
                    created_by="capability",
                )
                db.add(node)
                await db.commit()
                return "inserted"

            # Node exists — update if content or title changed.
            if existing.content == content and existing.title == title[:160]:
                return "unchanged"

            existing.title = title[:160]
            existing.content = content
            existing.metadata_ = full_meta
            await db.commit()
            return "updated"

        except Exception:
            await db.rollback()
            logger.exception(
                "ot2-protocols: _upsert_or_update_node failed for %s", external_id
            )
            raise
