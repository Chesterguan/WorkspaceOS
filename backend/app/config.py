from pydantic_settings import BaseSettings, SettingsConfigDict


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
    gemini_chat_model: str = "gemini-2.0-flash"
    gemini_embed_model: str = "text-embedding-004"

    # App security
    api_secret_key: str = "dev-secret-key"

    # Twitter/X API (OAuth 1.0a — required for user-context write access)
    twitter_api_key: str = ""        # Consumer key (API Key)
    twitter_api_secret: str = ""     # Consumer secret (API Secret)
    twitter_access_token: str = ""   # User access token
    twitter_access_secret: str = ""  # User access token secret

    # LinkedIn OAuth 2.0
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8989/api/v1/linkedin/callback"

    # Sync limits
    max_commits_per_sync: int = 50


settings = Settings()
