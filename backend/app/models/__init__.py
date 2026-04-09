# Import all models so that SQLAlchemy's metadata is fully populated before
# Alembic autogenerate or Base.metadata.create_all() is called.
from app.models.ai_feedback import AIFeedback
from app.models.blog import BlogPost, BlogPostVersion
from app.models.chat import ChatMessage
from app.models.draft import Draft
from app.models.memory import MemoryEntry
from app.models.narrative import Narrative
from app.models.posting import PostRecord, PostSchedule
from app.models.project import Project
from app.models.sync import GitHubCommit, GitHubRelease, SyncRun
from app.models.user import User
from app.models.venue import VenueCache
from app.models.workspace import WorkspaceSnapshot
from app.models.app_settings import AppSetting
from app.models.ai_usage import AIUsageLog
from app.models.worklog import WorkLog

__all__ = [
    "User",
    "Project",
    "Narrative",
    "SyncRun",
    "GitHubCommit",
    "GitHubRelease",
    "Draft",
    "MemoryEntry",
    "PostSchedule",
    "PostRecord",
    "BlogPost",
    "BlogPostVersion",
    "AIFeedback",
    "ChatMessage",
    "VenueCache",
    "WorkspaceSnapshot",
    "AppSetting",
    "AIUsageLog",
    "WorkLog",
]
