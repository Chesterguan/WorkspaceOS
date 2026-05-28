import logging
import sys
from typing import List, Tuple

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/pr_secretary"

    # GitHub
    github_token: str = ""

    # In-app feedback button → GitHub issue. Defaults to the upstream
    # WorkspaceOS repo; deployments can fork-redirect by overriding this
    # in .env (FEEDBACK_REPO=owner/repo). Empty disables the feature.
    feedback_repo: str = "Chesterguan/WorkspaceOS"

    # AI Provider selection (hybrid: local for privacy, cloud for quality)
    active_ai_provider: str = "openai"  # legacy compat
    local_ai_provider: str = "ollama"   # embeddings, extraction, consolidation
    cloud_ai_provider: str = "gemini"   # draft writing, blog generation, review

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_chat_model: str = "claude-sonnet-4-20250514"

    # Ollama (local models)
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"

    # Google Gemini
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"

    # App security
    api_secret_key: str = "dev-secret-key"
    jwt_secret_key: str = ""  # Falls back to api_secret_key if empty

    # Twitter/X API (OAuth 1.0a — required for user-context write access)
    twitter_api_key: str = ""        # Consumer key (API Key)
    twitter_api_secret: str = ""     # Consumer secret (API Secret)
    twitter_access_token: str = ""   # User access token
    twitter_access_secret: str = ""  # User access token secret

    # LinkedIn OAuth 2.0
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8989/api/v1/linkedin/callback"

    # Google OAuth 2.0 (Gmail + Calendar — currently Calendar only in use)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8989/api/v1/google/callback"

    # Microsoft Graph OAuth 2.0 (Outlook Calendar + Mail; Teams in future commit).
    # Uses tenant="common" so both personal @outlook.com and work/school
    # @company.com accounts can authenticate through the same registration.
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_redirect_uri: str = "http://localhost:8989/api/v1/microsoft/callback"

    # Dev.to (Forem) API
    devto_api_key: str = ""

    # Hashnode
    hashnode_api_key: str = ""
    hashnode_publication_id: str = ""

    # Google Drive (future)
    google_drive_credentials: str = ""
    # Notion (future)
    notion_api_key: str = ""

    # Explicit list of providers the paper-reviewer roundtable is allowed
    # to call directly. Bypasses CLOUD_AI_PROVIDER so the roundtable can
    # use multi-provider critique diversity (the deliberate design intent).
    # Empty list = roundtable uses only get_cloud_client().
    # See docs/privacy/known-leaks.md#l-2.
    paper_reviewer_providers: List[str] = []

    # Budget tracking
    daily_budget_warning_usd: float = 5.0  # warn when daily spend exceeds this

    # Sync limits
    max_commits_per_sync: int = 50


    def validate_startup(self) -> bool:
        """Validate required and optional env vars at startup.

        Returns True if all required vars are present. Logs warnings for
        missing optional vars. Logs FATAL + returns False for missing required vars.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Required: cloud AI provider key
        if self.cloud_ai_provider == "gemini" and not self.gemini_api_key:
            errors.append("GEMINI_API_KEY is required (cloud_ai_provider=gemini)")
        elif self.cloud_ai_provider == "openai" and not self.openai_api_key:
            errors.append("OPENAI_API_KEY is required (cloud_ai_provider=openai)")
        elif self.cloud_ai_provider == "anthropic" and not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required (cloud_ai_provider=anthropic)")

        # Required: API secret should not be the dev default in production
        if self.api_secret_key == "dev-secret-key":
            warnings.append(
                "API_SECRET_KEY is using the default 'dev-secret-key' — "
                "set a strong secret for production"
            )

        # Optional but important
        if not self.openai_api_key:
            warnings.append(
                "OPENAI_API_KEY not set — paper reviewer and roundtable critic "
                "will fall back to Gemini (less effective cross-model review)"
            )
        if not self.github_token:
            warnings.append(
                "GITHUB_TOKEN not set — GitHub sync, repo context, and release "
                "publishing will not work"
            )

        # Log results
        for w in warnings:
            logger.warning("CONFIG WARNING: %s", w)
        for e in errors:
            logger.critical("CONFIG FATAL: %s", e)

        if errors:
            logger.critical(
                "Startup aborted — %d required config var(s) missing. "
                "Check your .env file.",
                len(errors),
            )
            return False

        logger.info("Config validation passed (%d warnings)", len(warnings))
        return True


settings = Settings()
