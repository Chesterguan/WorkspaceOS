"""
Utilities for computing diffs between paper versions.

Uses stdlib difflib — no additional dependencies.
"""
import difflib
from typing import List


def compute_inline_diff(old_text: str, new_text: str) -> List[dict]:
    """
    Compute a line-by-line inline diff between two text strings.

    Returns a list of change records, each a dict with:
        type: "add" | "remove" | "same"
        content: the line text (without the leading +/-/space marker)

    The output preserves reading order so the caller can render a unified view.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    # unified_diff produces lines like "+added", "-removed", " same"
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            lineterm="",  # don't add extra newlines
            n=0,           # no context lines — caller can add if needed
        )
    )

    result: List[dict] = []
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            # Skip unified diff header lines
            continue
        if line.startswith("+"):
            result.append({"type": "add", "content": line[1:]})
        elif line.startswith("-"):
            result.append({"type": "remove", "content": line[1:]})
        else:
            result.append({"type": "same", "content": line[1:]})

    return result


def compute_diff_stats(old_text: str, new_text: str) -> dict:
    """
    Compute summary statistics for the diff between two text strings.

    Returns:
        lines_added: count of lines present in new_text but not old_text
        lines_removed: count of lines present in old_text but not new_text
        lines_changed: lines_added + lines_removed (total modified lines)
        similarity_pct: SequenceMatcher ratio * 100, rounded to 1 decimal place
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    lines_added = 0
    lines_removed = 0

    diff_lines = difflib.unified_diff(old_lines, new_lines, lineterm="", n=0)
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            lines_added += 1
        elif line.startswith("-"):
            lines_removed += 1

    matcher = difflib.SequenceMatcher(None, old_text, new_text)
    similarity_pct = round(matcher.ratio() * 100, 1)

    return {
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "lines_changed": lines_added + lines_removed,
        "similarity_pct": similarity_pct,
    }
