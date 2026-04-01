# Key Decisions Log

Append-only log of significant decisions made during development.

## Format
- [DATE] DECISION: description | WHY: reason | IMPACT: what it affects

## Decisions
- [2026-03-27] DECISION: Hybrid AI architecture (Ollama local + Gemini cloud + OpenAI review) | WHY: Privacy for code, quality for content, strong review | IMPACT: All AI services
- [2026-03-27] DECISION: Three-model agentic pipeline with privacy scan | WHY: No private data leaks to cloud | IMPACT: Draft generation flow
- [2026-03-27] DECISION: Mount local projects as read-only Docker volume | WHY: Workspace scanner needs filesystem access without write risk | IMPACT: Docker compose, scanner service
- [2026-03-29] DECISION: Twitter/X switched to manual copy-paste | WHY: Free tier API returns 402, Basic costs $100/mo | IMPACT: Publishing flow
- [2026-03-29] DECISION: Deep repo context fetches file tree, configs, PRs, issues — not just README | WHY: User found drafts were hallucinating without real project understanding | IMPACT: ai_generation, agentic_generation, repo_context
- [2026-03-29] DECISION: Agent harness pattern with state files + custom commands | WHY: Reduce token usage, enable task-executor workflow across sessions | IMPACT: Development workflow
- [2026-03-29] DECISION: All 50 API endpoints tested and passing | WHY: User wanted production-level reliability before moving on | IMPACT: Confidence in codebase
- [2026-03-29] DECISION: Embeddings changed from 1536-dim (zero-padded) to native 768-dim | WHY: Zero-padding destroyed cosine similarity making semantic search useless | IMPACT: memory_service, ai_client, migration 0004
- [2026-03-29] DECISION: Repo context cached 10min with reused HTTP client | WHY: Was making 10+ GitHub API calls per generation, risking rate limits | IMPACT: repo_context.py
- [2026-03-31] DECISION: Portfolio post feature for multi-project combined drafts | WHY: User wanted to post about multiple projects in one update | IMPACT: New /portfolio page, portfolio_template, generate_portfolio_draft
- [2026-03-31] DECISION: Global settings page for platform connections | WHY: User didn't want to re-connect LinkedIn per draft, connections should be configured once | IMPACT: /settings page, PublishButton links to settings
- [2026-04-01] DECISION: LinkedIn API version updated to 202603 | WHY: Versions 202401 and 202501 were expired (HTTP 426) | IMPACT: linkedin_service.py
