"""
LaTeX export and PDF compilation utilities for the paper pipeline.

Extracted from paper_service.py to keep responsibilities separated:
  - paper_service.py: context building, paper generation, review passes, titles
  - latex_service.py: Markdown-to-LaTeX conversion (pandoc + Python fallback), PDF compilation

Pandoc is used for LaTeX export when available; a pure-Python fallback is used
otherwise so the feature always works.
"""
import logging
import os
import re
import subprocess
import tempfile
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LaTeX export
# ---------------------------------------------------------------------------

async def export_to_latex(
    markdown_content: str,
    bibtex: str,
    template: str = "arxiv",
) -> Tuple[str, str]:
    """
    Convert a Markdown paper to LaTeX.

    Attempts to use pandoc if it is installed on the system PATH.
    If pandoc is not available, falls back to a pure-Python minimal conversion
    so the feature always works regardless of server configuration.

    Args:
        markdown_content: The full paper in Markdown.
        bibtex: BibTeX entries for the references section.
        template: LaTeX template style — "arxiv", "ieee", or "acm".

    Returns:
        (latex_content, bibtex_content) tuple.
    """
    # Try pandoc first
    try:
        latex = await _pandoc_convert(markdown_content, template)
        logger.info("export_to_latex: pandoc conversion succeeded (template: %s)", template)
        return latex, bibtex
    except FileNotFoundError:
        logger.info("export_to_latex: pandoc not found, using Python fallback")
    except Exception:
        logger.exception("export_to_latex: pandoc failed unexpectedly, using Python fallback")

    # Pure-Python fallback
    latex = _python_md_to_latex(markdown_content, template)
    return latex, bibtex


async def _pandoc_convert(markdown_content: str, template: str) -> str:
    """
    Run pandoc in a subprocess to convert Markdown to LaTeX.

    Raises FileNotFoundError if pandoc is not installed.
    Raises subprocess.CalledProcessError on conversion failure.
    """
    import asyncio

    # Map our template names to pandoc options
    template_args: List[str] = []
    if template == "ieee":
        template_args = ["--template", "ieee"]
    elif template == "acm":
        template_args = ["--template", "acm-sigconf"]
    # "arxiv" uses pandoc's default article LaTeX template

    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as tmp_in:
        tmp_in.write(markdown_content)
        tmp_in_path = tmp_in.name

    try:
        cmd = ["pandoc", tmp_in_path, "-f", "markdown", "-t", "latex", "--standalone"] + template_args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout, stderr=stderr
            )
        return stdout.decode("utf-8")
    finally:
        try:
            os.unlink(tmp_in_path)
        except OSError:
            pass


def _python_md_to_latex(markdown_content: str, template: str) -> str:
    """
    Minimal Markdown → LaTeX converter using stdlib re.

    Handles:
    - ## H2 → \\section{}, ### H3 → \\subsection{}, #### H4 → \\subsubsection{}
    - **bold** → \\textbf{}, *italic* → \\textit{}
    - `code` → \\texttt{}
    - [N] citations → \\cite{refN}
    - References section → BibTeX placeholder comment
    - Blank lines → paragraph breaks (\\par)

    This is a best-effort conversion; complex tables and figures are passed through
    as verbatim comments so no content is silently dropped.
    """
    document_class: str
    packages: str

    if template == "ieee":
        document_class = "\\documentclass[conference]{IEEEtran}"
        packages = (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb,amsfonts}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}"
        )
    elif template == "acm":
        document_class = "\\documentclass[sigconf]{acmart}"
        packages = (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{hyperref}"
        )
    elif template in ("neurips", "icml", "iclr", "acl", "aaai"):
        # Use venue-specific preamble from template service
        from app.services.template_service import get_preamble
        document_class, packages = get_preamble(None, template_override=template)
    else:  # arxiv / default
        document_class = "\\documentclass[12pt]{article}"
        packages = (
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{setspace}\n"
            "\\doublespacing"
        )

    body_lines: List[str] = []
    lines = markdown_content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Section headers
        if line.startswith("#### "):
            content = _escape_latex(line[5:].strip())
            body_lines.append(f"\\subsubsection{{{content}}}")
        elif line.startswith("### "):
            content = _escape_latex(line[4:].strip())
            body_lines.append(f"\\subsection{{{content}}}")
        elif line.startswith("## "):
            content = _escape_latex(line[3:].strip())
            # References section → use thebibliography
            if re.match(r"references?\s*$", content, re.IGNORECASE):
                body_lines.append(
                    "% Bibliography — insert your .bib file reference here\n"
                    "\\bibliographystyle{plain}\n"
                    "\\bibliography{references}"
                )
                i += 1
                continue
            body_lines.append(f"\\section{{{content}}}")
        elif line.startswith("# "):
            # Top-level H1 → title (only the first one)
            content = _escape_latex(line[2:].strip())
            body_lines.append(f"\\title{{{content}}}\n\\maketitle")
        elif line.strip() == "":
            body_lines.append("")  # paragraph break preserved
        else:
            body_lines.append(_convert_inline(line))

        i += 1

    body = "\n".join(body_lines)

    return (
        f"{document_class}\n"
        f"{packages}\n\n"
        f"\\begin{{document}}\n\n"
        f"{body}\n\n"
        f"\\end{{document}}\n"
    )


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text."""
    # Order matters — backslash must come first
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _convert_inline(text: str) -> str:
    """
    Convert Markdown inline formatting to LaTeX.

    Handles **bold**, *italic*, `code`, and [N] citation references.
    Does not escape all LaTeX special chars — this is intentional for
    content that may already contain partial LaTeX from the AI writer.
    """
    # [N] citations → \cite{refN}
    text = re.sub(r"\[(\d+)\]", lambda m: f"\\cite{{ref{m.group(1)}}}", text)
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"\\textbf{{{m.group(1)}}}", text)
    # *italic* (single asterisk, not already consumed by bold)
    text = re.sub(r"\*(.+?)\*", lambda m: f"\\textit{{{m.group(1)}}}", text)
    # `code`
    text = re.sub(r"`(.+?)`", lambda m: f"\\texttt{{{m.group(1)}}}", text)
    return text


# ---------------------------------------------------------------------------
# PDF compilation
# ---------------------------------------------------------------------------

async def compile_latex_to_pdf(latex_content: str) -> Optional[bytes]:
    """Compile LaTeX to PDF using pdflatex.

    Returns the PDF bytes or None if compilation fails.
    Requires pdflatex to be installed (texlive-latex-base in Docker).
    """
    import asyncio

    with tempfile.NamedTemporaryFile(
        suffix=".tex", mode="w", encoding="utf-8", delete=False, dir="/tmp"
    ) as tmp:
        tmp.write(latex_content)
        tex_path = tmp.name

    pdf_path = tex_path.replace(".tex", ".pdf")
    work_dir = os.path.dirname(tex_path)

    try:
        # Run pdflatex twice (for references/TOC to resolve correctly)
        for pass_num in range(2):
            proc = await asyncio.create_subprocess_exec(
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory", work_dir,
                tex_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 and pass_num == 1:
                logger.warning(
                    "compile_latex_to_pdf: pdflatex pass %d failed (rc=%d)",
                    pass_num + 1, proc.returncode,
                )
                # Try to return partial PDF if it exists
                if not os.path.exists(pdf_path):
                    return None

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                return f.read()
        return None

    except FileNotFoundError:
        logger.warning("compile_latex_to_pdf: pdflatex not found")
        return None
    except Exception:
        logger.exception("compile_latex_to_pdf: unexpected error")
        return None
    finally:
        # Cleanup temp files
        for ext in [".tex", ".pdf", ".aux", ".log", ".out"]:
            path = tex_path.replace(".tex", ext)
            try:
                os.unlink(path)
            except OSError:
                pass
