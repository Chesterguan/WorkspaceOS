"""
Prompt templates for each supported publishing platform.
Templates receive a context dict and return a (system, user) tuple.

Supported keys for each template are documented in the function's docstring.
"""
from typing import Tuple


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


# Registry mapping platform slug -> template function
TEMPLATE_REGISTRY = {
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
