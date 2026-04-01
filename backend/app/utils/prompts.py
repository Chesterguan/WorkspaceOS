"""
Prompt templates for each supported publishing platform.
Templates receive a context dict and return a (system, user) tuple.

Supported keys for each template are documented in the function's docstring.
"""
from typing import List, Tuple


def _base_system(extra: str = "") -> str:
    base = (
        "You are an expert technical content writer who specialises in developer tools and "
        "open-source projects. Write in an authentic, conversational voice — never generic "
        "corporate marketing speak. Be specific and concrete; always lead with value to the reader."
    )
    return f"{base}\n\n{extra}".strip()


def _repo_context_section(ctx: dict) -> str:
    """Build the live repository context section for injection into prompts."""
    parts = []
    if ctx.get("repo_context"):
        parts.append(f"## Live Repository Context\n{ctx['repo_context']}")
    if ctx.get("readme_content") and not ctx.get("repo_context"):
        # Only include stored README if live context isn't available
        parts.append(f"## README\n{ctx['readme_content']}")
    if ctx.get("release_notes"):
        parts.append(f"## Recent Releases\n{ctx['release_notes']}")
    return "\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Platform templates
# ---------------------------------------------------------------------------

PLATFORM_TEMPLATES: dict[str, tuple[str, str]] = {}


def linkedin_template(ctx: dict) -> tuple[str, str]:
    system = _base_system(
        "You write for LinkedIn: professional but human. Posts should be 150-300 words, "
        "start with a punchy hook (no 'I am excited to announce'), use short paragraphs, "
        "and end with a clear call-to-action. Include 3-5 relevant hashtags on the last line."
    )
    repo_section = _repo_context_section(ctx)
    user = f"""Write a LinkedIn post about the following project update.

## Project
Name: {ctx.get('project_name')}
GitHub: {ctx.get('github_url', '')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience: {ctx.get('target_audience', 'N/A')}

{repo_section}

## Recent changes
{ctx.get('changes_summary', 'No specific changes provided.')}

## Narrative guidance
Preferred angles: {', '.join(ctx.get('preferred_angles') or ['Not specified'])}
Avoided angles: {', '.join(ctx.get('avoided_angles') or ['None'])}
Tone notes: {ctx.get('tone_notes', 'N/A')}
User preference patterns: {ctx.get('preference_context', 'No preference history yet.')}

## Relevant memory
{ctx.get('memory_context', 'No additional context.')}

When linking to the project, use this exact URL: {ctx.get('github_url', '')} — never use placeholder links.

Write the LinkedIn post now."""
    return system, user


def twitter_template(ctx: dict) -> tuple[str, str]:
    system = _base_system(
        "You write Twitter/X threads for developer audiences. Each tweet must be under 280 "
        "characters. Format as a numbered thread (1/, 2/, ...) of 5-8 tweets. "
        "The first tweet is the hook — make it worth clicking. End with a reply-bait question."
    )
    repo_section = _repo_context_section(ctx)
    user = f"""Write a Twitter thread about the following project update.

## Project
Name: {ctx.get('project_name')}
GitHub: {ctx.get('github_url', '')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience: {ctx.get('target_audience', 'N/A')}

{repo_section}

## Recent changes
{ctx.get('changes_summary', 'No specific changes provided.')}

## Narrative guidance
Preferred angles: {', '.join(ctx.get('preferred_angles') or ['Not specified'])}
Tone notes: {ctx.get('tone_notes', 'N/A')}
User preference patterns: {ctx.get('preference_context', 'No preference history yet.')}

When linking to the project, use this exact URL: {ctx.get('github_url', '')} — never use placeholder links.

Write the thread now. Strictly ≤280 chars per tweet."""
    return system, user


def xiaohongshu_template(ctx: dict) -> tuple[str, str]:
    system = _base_system(
        "You write posts for Xiaohongshu (小红书 / RedNote), a Chinese lifestyle and knowledge "
        "platform popular with tech-savvy young professionals. Write in Simplified Chinese. "
        "Use a warm, personal diary-style voice. Include an emoji-rich title line, 3-5 short "
        "sections with section titles using emojis, and end with 5-10 hashtags in Chinese."
    )
    repo_section = _repo_context_section(ctx)
    user = f"""为以下项目更新写一篇小红书帖子。

## 项目信息
项目名称: {ctx.get('project_name')}
GitHub: {ctx.get('github_url', '')}
一句话介绍: {ctx.get('one_liner', '暂无')}
目标用户: {ctx.get('target_audience', '暂无')}

{repo_section}

## 最近更新
{ctx.get('changes_summary', '暂无具体更新内容。')}

## 内容方向
推荐角度: {', '.join(ctx.get('preferred_angles') or ['未指定'])}
语气备注: {ctx.get('tone_notes', '暂无')}

如需提供项目链接，请使用此确切URL：{ctx.get('github_url', '')} — 请勿使用占位链接。

请用中文撰写小红书帖子。"""
    return system, user


def medium_outline_template(ctx: dict) -> tuple[str, str]:
    system = _base_system(
        "You write detailed article outlines for Medium. The outline must include: "
        "a working title, a subtitle, an intro paragraph, 4-6 sections with H2 headings and "
        "3-4 bullet points each describing what that section will cover, a conclusion section, "
        "and suggested SEO tags. Format in Markdown."
    )
    repo_section = _repo_context_section(ctx)
    user = f"""Create a Medium article outline about the following project.

## Project
Name: {ctx.get('project_name')}
GitHub: {ctx.get('github_url', '')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience: {ctx.get('target_audience', 'N/A')}
Origin story: {ctx.get('origin_story', 'N/A')}

{repo_section}

## Recent changes to cover
{ctx.get('changes_summary', 'No specific changes provided.')}

## Narrative guidance
Preferred angles: {', '.join(ctx.get('preferred_angles') or ['Not specified'])}
Avoided angles: {', '.join(ctx.get('avoided_angles') or ['None'])}
Tone notes: {ctx.get('tone_notes', 'N/A')}
User preference patterns: {ctx.get('preference_context', 'No preference history yet.')}

## FAQ to draw from
{ctx.get('faq_text', 'None provided.')}

When linking to the project, use this exact URL: {ctx.get('github_url', '')} — never use placeholder links.

Produce the outline in Markdown now."""
    return system, user


def github_release_template(ctx: dict) -> tuple[str, str]:
    system = _base_system(
        "You write GitHub release notes for developer audiences. The release notes must be "
        "structured Markdown: a one-paragraph summary of what changed and why it matters, "
        "then sections for 'What's New', 'Bug Fixes' (if any), 'Breaking Changes' (if any), "
        "and 'Full Changelog' (just a placeholder link line). Be precise and factual. "
        "No marketing fluff — developers will read this to decide whether to upgrade."
    )
    repo_section = _repo_context_section(ctx)
    user = f"""Write GitHub release notes for the following release.

## Project
Name: {ctx.get('project_name')}
GitHub: {ctx.get('github_url', '')}
One-liner: {ctx.get('one_liner', 'N/A')}

{repo_section}

## Release
Tag: {ctx.get('tag_name', 'vX.Y.Z')}
Release name: {ctx.get('release_name', 'N/A')}

## Commits since last release
{ctx.get('changes_summary', 'No commit data provided.')}

## Previous release body (for context)
{ctx.get('previous_release_body', 'N/A')}

## Narrative guidance
User preference patterns: {ctx.get('preference_context', 'No preference history yet.')}

When linking to the project or changelog, use this exact repo URL: {ctx.get('github_url', '')} — never use placeholder links.

Write the release notes now."""
    return system, user


def evolution_summary_template(ctx: dict) -> tuple[str, str]:
    system = _base_system(
        "You write concise internal evolution summaries for software projects. "
        "The summary should be 2-4 paragraphs that describe what changed, why it likely "
        "changed based on commit messages, and what this signals about project direction. "
        "Write in plain prose, no bullet points. This is read by the project owner, not the public."
    )
    user = f"""Summarise the evolution captured in the following sync run.

## Project
Name: {ctx.get('project_name')}
Repo: {ctx.get('github_repo', 'N/A')}

## Commits ({ctx.get('commit_count', 0)} total)
{ctx.get('commit_list', 'No commits.')}

## Releases fetched
{ctx.get('release_list', 'No releases.')}

Write the evolution summary now."""
    return system, user


def blog_post_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate a full long-form blog post in Markdown.

    Required ctx keys: project_name, post_title, changes_summary, memory_context.
    Optional ctx keys: one_liner, target_audience, origin_story, preferred_angles,
                       avoided_angles, tone_notes, context_hint, readme_content.
    """
    system = _base_system(
        "You write long-form technical blog posts in Markdown. Structure your posts clearly with "
        "an engaging introduction, well-organised H2/H3 sections, code examples where relevant, "
        "and a concise conclusion. Write at a level appropriate for technical practitioners. "
        "Avoid listicle padding — every sentence should add value."
    )
    repo_section = _repo_context_section(ctx)
    user = f"""Write a complete blog post in Markdown for the following project.

## Post Title
{ctx.get('post_title')}

## Project
Name: {ctx.get('project_name')}
GitHub: {ctx.get('github_url', '')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience: {ctx.get('target_audience', 'N/A')}
Origin story: {ctx.get('origin_story', 'N/A')}

{repo_section}

## Recent changes to feature
{ctx.get('changes_summary', 'No specific changes provided.')}

## Narrative guidance
Preferred angles: {', '.join(ctx.get('preferred_angles') or ['Not specified'])}
Avoided angles: {', '.join(ctx.get('avoided_angles') or ['None'])}
Tone notes: {ctx.get('tone_notes', 'N/A')}

## Relevant memory / context
{ctx.get('memory_context', 'No additional context.')}

## Additional hint
{ctx.get('context_hint', 'No specific hint provided.')}

When linking to the project, use this exact URL: {ctx.get('github_url', '')} — never use placeholder links.

Write the complete blog post in Markdown now."""
    return system, user


def review_template(ctx: dict) -> Tuple[str, str]:
    """
    AI self-review template used in the agentic generation loop.

    Required ctx keys: platform, draft_content, project_name.
    """
    system = _base_system(
        "You are a strict senior editor reviewing AI-generated content. Your job is to give "
        "honest, constructive critique. Always end your review with a numeric score on the last "
        "line in the format 'Score: N' where N is 0-10. Be specific about what to improve."
    )
    user = f"""Review the following {ctx.get('platform', 'content')} draft for the project "{ctx.get('project_name')}".

Evaluate it on these criteria:
1. Specificity — does it reference concrete details, or is it vague and generic?
2. Voice — is it authentic and human, or does it sound like corporate marketing?
3. Structure — is the format appropriate for the platform?
4. Value to the reader — does the opening hook grab attention? Does the content deliver?
5. Accuracy — are there any claims that seem unsupported or unlikely?

## Draft to review
{ctx.get('draft_content', '')}

Provide your detailed critique, then end with exactly: Score: N"""
    return system, user


def extraction_template(ctx: dict) -> Tuple[str, str]:
    """
    Extract high-level themes from a list of commits and releases.

    Required ctx keys: commit_list, release_list, commit_count, release_count.
    """
    system = _base_system(
        "You are a technical analyst extracting meaningful themes from software development "
        "activity. Identify the key technical decisions, feature areas, and strategic directions "
        "reflected in the given commits and releases. Be concise and factual."
    )
    user = f"""Analyse the following {ctx.get('commit_count', 0)} commits and {ctx.get('release_count', 0)} releases and extract the key themes.

## Commits
{ctx.get('commit_list', 'No commits.')}

## Releases
{ctx.get('release_list', 'No releases.')}

Output one theme per line. Each theme should be a single clear sentence describing a meaningful pattern, decision, or area of work visible in these changes. Do not include bullet points or numbering — just one theme per line."""
    return system, user


def consolidation_template(ctx: dict) -> Tuple[str, str]:
    """
    Synthesise a large set of memory entries into a compact consolidated summary.

    Required ctx keys: entry_count, entries_text.
    """
    system = _base_system(
        "You are synthesising a project's accumulated knowledge from many memory entries into a "
        "single dense, coherent summary. The summary must preserve all important facts, decisions, "
        "and context while being as concise as possible. Write in plain prose, no bullet points."
    )
    user = f"""The following {ctx.get('entry_count', 0)} memory entries were recorded for a software project. Synthesise them into a single comprehensive summary paragraph (200-400 words) that captures the project's purpose, key technical decisions, important context, and development direction.

## Memory entries
{ctx.get('entries_text', 'No entries.')}

Write the consolidated summary now."""
    return system, user


def portfolio_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate a cohesive post covering multiple projects.

    Required ctx keys: platform, projects (list of dicts with keys:
        name, github_url, one_liner, repo_context, memory_context, changes_summary).
    Optional ctx keys: theme, additional_context.
    """
    platform = ctx.get("platform", "linkedin")
    theme = ctx.get("theme", "")
    theme_instruction = f"The overall theme of this post is: {theme}." if theme else ""

    platform_instructions = {
        "linkedin": (
            "You write for LinkedIn: professional but human. Posts should be 200-350 words, "
            "start with a punchy hook (no 'I am excited to announce'), use short paragraphs, "
            "weave all projects together into a coherent narrative, and end with a clear "
            "call-to-action. Include 3-5 relevant hashtags on the last line."
        ),
        "twitter": (
            "You write Twitter/X threads for developer audiences. Each tweet must be under 280 "
            "characters. Format as a numbered thread (1/, 2/, ...) of 6-10 tweets that covers "
            "all projects. The first tweet is the hook — make it worth clicking. End with a "
            "reply-bait question."
        ),
        "xiaohongshu": (
            "You write posts for Xiaohongshu (小红书 / RedNote) in Simplified Chinese. "
            "Use a warm, personal diary-style voice. Include an emoji-rich title line, "
            "cover each project in its own section with emoji titles, and end with 5-10 "
            "hashtags in Chinese."
        ),
        "medium_outline": (
            "You write detailed article outlines for Medium. The outline must include: "
            "a working title, a subtitle, an intro paragraph, one H2 section per project "
            "with 3-4 bullet points each, a cross-project synthesis section, and suggested "
            "SEO tags. Format in Markdown."
        ),
    }
    platform_hint = platform_instructions.get(
        platform, platform_instructions["linkedin"]
    )

    # Build the per-project context blocks
    projects = ctx.get("projects", [])
    project_sections: List[str] = []
    for i, proj in enumerate(projects, start=1):
        section_lines = [
            f"### Project {i}: {proj.get('name', 'Unknown')}",
            f"GitHub: {proj.get('github_url', 'N/A')}",
            f"One-liner: {proj.get('one_liner', 'N/A')}",
        ]
        if proj.get("changes_summary"):
            section_lines.append(f"Recent changes: {proj['changes_summary']}")
        if proj.get("repo_context"):
            # Keep repo context brief for multi-project prompts
            rc = proj["repo_context"]
            if len(rc) > 1500:
                rc = rc[:1500] + "\n... (truncated)"
            section_lines.append(f"Repository context:\n{rc}")
        if proj.get("memory_context"):
            section_lines.append(f"Relevant memory:\n{proj['memory_context']}")
        project_sections.append("\n".join(section_lines))

    projects_block = "\n\n".join(project_sections)

    system = _base_system(platform_hint)
    user = f"""Write a single {platform} post that covers ALL of the following projects in a cohesive way.

{theme_instruction}

Do NOT write separate posts per project — weave them together into one unified narrative.
Reference the GitHub URL for each project exactly as provided — never use placeholder links.

## Projects to cover

{projects_block}

## Additional context
{ctx.get('additional_context', 'None provided.')}

Write the {platform} post now."""
    return system, user


def preference_context_template(ctx: dict) -> Tuple[str, str]:
    """
    Produce a prose block describing user content preferences derived from feedback.
    This is used as a standalone utility template — not a generation template.

    Required ctx keys: preference_summary.
    """
    system = _base_system(
        "You summarise user content preferences in a clear, actionable way for AI generation guidance."
    )
    user = f"""Summarise the following preference data for use in future content generation:

{ctx.get('preference_summary', 'No preference data available.')}

Write a concise guidance paragraph that a content generator should follow."""
    return system, user


# ---------------------------------------------------------------------------
# Research writing templates
# ---------------------------------------------------------------------------

def _research_base_system(output_type: str, extra: str = "") -> str:
    """Base system prompt for all research writing templates."""
    base = (
        f"You are an expert academic writer producing a {output_type}. "
        "Write with formal academic precision. Every factual claim about the literature must be "
        "backed by a [N] citation referencing the numbered papers in the Available Literature "
        "section. Never fabricate paper titles, authors, or DOIs. Use only papers explicitly "
        "listed in the provided context. Quantitative claims must be drawn from project data "
        "or cited literature. End your output with a numbered References section listing every "
        "paper you cited."
    )
    return f"{base}\n\n{extra}".strip()


def _literature_section(ctx: dict) -> str:
    """Inject the Semantic Scholar literature block into a prompt."""
    lit = ctx.get("literature_context") or ""
    if lit:
        return f"\n{lit}\n"
    return "\n(No literature context provided — do not fabricate citations.)\n"


def research_grant_proposal_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate an NIH/NSF-style grant proposal.

    Required ctx keys: project_name, one_liner, target_audience.
    Optional ctx keys: literature_context, repo_context, workspace_context,
                       origin_story, preferred_angles, funding_agency, project_period.
    """
    agency = ctx.get("funding_agency", "NSF")
    system = _research_base_system(
        f"{agency}-style grant proposal",
        "Structure the proposal with clearly labelled sections. "
        f"Write as if submitting to {agency}. "
        "Specific Aims should be one page maximum. "
        "Significance must establish the gap in current knowledge with citations. "
        "Innovation must distinguish this work from prior art using [N] citations. "
        "Approach must describe a concrete technical plan with milestones.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write a complete {agency}-style grant proposal for the following project.

## Project
Name: {ctx.get('project_name', 'N/A')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience / beneficiaries: {ctx.get('target_audience', 'N/A')}
Origin story / motivation: {ctx.get('origin_story', 'N/A')}
Funding agency: {agency}
Project period: {ctx.get('project_period', '3 years')}

## Available Literature (cite using [N] notation)
{lit_section}

## Repository / Technical Context
{ctx.get('repo_context', 'No repository context provided.')}

## Workspace Context
{ctx.get('workspace_context', 'No workspace context provided.')}

## Research Angles
{', '.join(ctx.get('preferred_angles') or ['Not specified'])}

Produce the complete grant proposal with the following sections:
1. Specific Aims (one page equivalent)
2. Significance (establish the problem and gap with [N] citations)
3. Innovation (what is new; compare to prior art with [N] citations)
4. Approach (technical plan, preliminary data, milestones, risks and mitigations)
5. Broader Impacts / Significance to Society

End with a numbered References section for every paper cited."""
    return system, user


def research_conference_abstract_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate a 250-word structured conference abstract.

    Required ctx keys: project_name, one_liner.
    Optional ctx keys: literature_context, repo_context, target_venue, results_summary.
    """
    venue = ctx.get("target_venue", "a peer-reviewed conference")
    system = _research_base_system(
        f"250-word structured conference abstract for {venue}",
        "Format: Background/Objective (1-2 sentences), Methods (2-3 sentences), "
        "Results/Contributions (2-3 sentences with specific numbers where available), "
        "Conclusion/Significance (1-2 sentences). "
        "Total word count must be 230-270 words. "
        "Include exactly 3-5 keywords on the last line prefixed with 'Keywords:'.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write a structured 250-word conference abstract for the following project.

## Project
Name: {ctx.get('project_name', 'N/A')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target venue: {venue}

## Available Literature
{lit_section}

## Technical Context
{ctx.get('repo_context', 'No repository context provided.')}

## Known Results / Contributions
{ctx.get('results_summary', 'Describe contributions from the project context.')}

Write the abstract now. Strictly 230-270 words. End with Keywords line."""
    return system, user


def research_paper_intro_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate an introduction section with full literature positioning.

    Required ctx keys: project_name, one_liner.
    Optional ctx keys: literature_context, repo_context, target_venue, research_gap.
    """
    venue = ctx.get("target_venue", "a peer-reviewed venue")
    system = _research_base_system(
        f"conference/journal paper introduction section for {venue}",
        "Structure: (1) Opening motivation — why the problem matters, with real-world evidence. "
        "(2) Background — what is known, with [N] citations for each prior approach. "
        "(3) Gap — what is missing or insufficient in current work, citing specific limitations. "
        "(4) Contribution statement — bulleted list of the paper's specific contributions. "
        "(5) Paper structure — one sentence per section ('Section 2 describes...'). "
        "Length: 4-6 paragraphs. Every paragraph that makes a claim about prior work must have [N] citations.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write a complete introduction section for a paper about the following project.

## Project
Name: {ctx.get('project_name', 'N/A')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target venue: {venue}
Research gap this work addresses: {ctx.get('research_gap', 'Derive from context and literature.')}

## Available Literature (cite using [N] notation)
{lit_section}

## Technical Context (for contribution statement)
{ctx.get('repo_context', 'No repository context provided.')}

Write the introduction section now. End with a References section."""
    return system, user


def research_paper_methods_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate a methods section derived from actual codebase architecture.

    Required ctx keys: project_name.
    Optional ctx keys: literature_context, repo_context, workspace_context, target_venue.
    """
    venue = ctx.get("target_venue", "a peer-reviewed venue")
    system = _research_base_system(
        f"methods section for a paper submitted to {venue}",
        "Ground every architectural description in the actual repository and workspace context provided. "
        "Structure: (1) System Overview (high-level diagram described in prose), "
        "(2) Data Pipeline / Inputs, (3) Core Algorithms or Models — use [N] citations for "
        "any technique borrowed from prior work, (4) Implementation Details (languages, frameworks, "
        "key libraries — from the actual tech stack), (5) Evaluation Metrics. "
        "Do not invent components not visible in the code context. "
        "Describe what the system actually does.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write a complete methods section for a paper about the following system.

## Project
Name: {ctx.get('project_name', 'N/A')}
Target venue: {venue}

## Available Literature (cite borrowed techniques using [N] notation)
{lit_section}

## Repository Context (the ACTUAL implementation to describe)
{ctx.get('repo_context', 'No repository context provided.')}

## Workspace Context
{ctx.get('workspace_context', 'No workspace context provided.')}

Write the methods section now. Reference actual files, frameworks, and components from the context. End with a References section for any cited techniques."""
    return system, user


def research_literature_review_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate a structured related work / literature review section.

    Required ctx keys: project_name, one_liner.
    Optional ctx keys: literature_context, research_gap, target_venue.
    """
    system = _research_base_system(
        "related work / literature review section",
        "Organise thematically, not chronologically. "
        "Each theme paragraph: introduce the theme, cite 2-4 papers [N] that represent the approach, "
        "describe their contributions and limitations. "
        "Final paragraph: synthesise the gap — what existing work collectively fails to address, "
        "and how this project's approach differs. "
        "Do NOT describe the current project's solution in the literature review — that belongs in contributions. "
        "Every paper referenced must come from the Available Literature context.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write a complete related work / literature review section for the following project.

## Project
Name: {ctx.get('project_name', 'N/A')}
One-liner: {ctx.get('one_liner', 'N/A')}
Research gap: {ctx.get('research_gap', 'Derive from the literature context below.')}

## Available Literature (the ONLY papers you may cite — use [N] notation)
{lit_section}

Write the literature review now. Organise thematically. End with a gap synthesis paragraph and a References section."""
    return system, user


def research_technical_report_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate a full technical report with executive summary.

    Required ctx keys: project_name, one_liner.
    Optional ctx keys: literature_context, repo_context, workspace_context,
                       target_audience, results_summary.
    """
    system = _research_base_system(
        "full technical report",
        "Include all major sections. Write for a technical expert audience who will "
        "implement or evaluate the system. Every design decision should be justified. "
        "Where the project has known results, cite them with specifics. "
        "Where results are pending, describe the evaluation plan.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write a complete technical report for the following project.

## Project
Name: {ctx.get('project_name', 'N/A')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience: {ctx.get('target_audience', 'Technical practitioners and researchers')}

## Available Literature
{lit_section}

## Technical Context (repository and workspace)
Repository: {ctx.get('repo_context', 'No repository context provided.')}
Workspace: {ctx.get('workspace_context', 'No workspace context provided.')}

## Known Results / Contributions
{ctx.get('results_summary', 'Describe contributions from the project context.')}

Produce the complete technical report with:
1. Executive Summary (1 page equivalent — problem, approach, key findings)
2. Introduction (motivation, scope, report structure)
3. Background and Related Work (with [N] citations)
4. System Design and Architecture (from actual codebase)
5. Implementation (tech stack, key components, engineering decisions)
6. Evaluation / Results (actual or planned)
7. Discussion (limitations, future work)
8. Conclusion
9. References

Write the full report now."""
    return system, user


def research_white_paper_template(ctx: dict) -> Tuple[str, str]:
    """
    Generate an industry-facing white paper for non-academic audiences.

    Required ctx keys: project_name, one_liner.
    Optional ctx keys: literature_context, repo_context, target_audience, results_summary.
    """
    system = _research_base_system(
        "industry white paper",
        "Write for a non-academic audience: CTOs, product managers, policy makers, or domain experts. "
        "Lead with the business/social problem. Avoid jargon without explanation. "
        "Use [N] citations sparingly — only for key statistics or findings that establish credibility. "
        "Include an executive summary, clear problem statement, solution overview, evidence, "
        "and a concrete call to action. Use headers, short paragraphs, and bullet lists for scannability.",
    )
    lit_section = _literature_section(ctx)
    user = f"""Write an industry white paper for the following project.

## Project
Name: {ctx.get('project_name', 'N/A')}
One-liner: {ctx.get('one_liner', 'N/A')}
Target audience: {ctx.get('target_audience', 'Industry professionals and decision-makers')}

## Supporting Literature (cite key statistics/findings with [N])
{lit_section}

## Technical Evidence
{ctx.get('repo_context', 'No repository context provided.')}

## Known Results
{ctx.get('results_summary', 'Describe key outcomes from the project context.')}

Produce the white paper with:
1. Executive Summary (3-5 bullet points)
2. The Problem (real-world impact, scale, urgency — with [N] citations for statistics)
3. Why Existing Solutions Fall Short
4. Our Approach (accessible technical description, no jargon)
5. Evidence and Results
6. Call to Action / Next Steps
7. References (for any [N] citations used)

Write the white paper now."""
    return system, user


# Registry mapping platform slug -> template function
TEMPLATE_REGISTRY = {
    "portfolio": portfolio_template,
    "linkedin": linkedin_template,
    "twitter": twitter_template,
    "xiaohongshu": xiaohongshu_template,
    "medium_outline": medium_outline_template,
    "github_release": github_release_template,
    "evolution_summary": evolution_summary_template,
    "blog_post": blog_post_template,
    "review": review_template,
    "extraction": extraction_template,
    "consolidation": consolidation_template,
    "preference_context": preference_context_template,
    # Research writing templates
    "research_grant_proposal": research_grant_proposal_template,
    "research_conference_abstract": research_conference_abstract_template,
    "research_paper_intro": research_paper_intro_template,
    "research_paper_methods": research_paper_methods_template,
    "research_literature_review": research_literature_review_template,
    "research_technical_report": research_technical_report_template,
    "research_white_paper": research_white_paper_template,
}


def get_template(platform: str):
    """Return the template function for the given platform slug.

    Raises KeyError if the platform is not recognised.
    """
    template_fn = TEMPLATE_REGISTRY.get(platform)
    if template_fn is None:
        supported = ", ".join(TEMPLATE_REGISTRY.keys())
        raise KeyError(f"Unknown platform '{platform}'. Supported: {supported}")
    return template_fn
