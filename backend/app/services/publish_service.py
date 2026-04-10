"""
Publishing service: auto-publish drafts to external platforms.

Errors from the platform APIs are caught and returned as structured error
responses rather than raised, so callers never receive a 500 for a publishing
failure (e.g. bad token, duplicate tag name, rate-limit hit).
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.draft import Draft
from app.models.posting import PostRecord
from app.models.project import Project
from app.services import linkedin_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _load_project(project_id: uuid.UUID, db: AsyncSession) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def _load_draft(draft_id: uuid.UUID, db: AsyncSession) -> Optional[Draft]:
    result = await db.execute(select(Draft).where(Draft.id == draft_id))
    return result.scalar_one_or_none()


async def _create_post_record(
    draft_id: uuid.UUID,
    project_id: uuid.UUID,
    platform: str,
    post_url: Optional[str],
    db: AsyncSession,
) -> PostRecord:
    """Persist a PostRecord and flush so its id is available immediately."""
    record = PostRecord(
        draft_id=draft_id,
        project_id=project_id,
        platform=platform,
        posted_at=datetime.now(timezone.utc),
        post_url=post_url,
        post_type="auto",
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


def _github_headers() -> Dict[str, str]:
    """Standard headers required by the GitHub REST API."""
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {settings.github_token}",
    }


def _twitter_headers() -> Dict[str, str]:
    """OAuth 1.0a signed headers for Twitter API v2 user-context writes."""
    # httpx does not handle OAuth 1.0a natively; we build it via requests_oauthlib
    # imported lazily so that missing the optional dep only fails at call time.
    from requests_oauthlib import OAuth1  # type: ignore
    auth = OAuth1(
        settings.twitter_api_key,
        settings.twitter_api_secret,
        settings.twitter_access_token,
        settings.twitter_access_secret,
    )
    # requests_oauthlib mutates a PreparedRequest; extract the Authorization
    # header by signing a dummy request.
    import requests  # type: ignore
    req = requests.Request("POST", "https://api.twitter.com/2/tweets", json={})
    prepared = req.prepare()
    auth(prepared)
    return {"Authorization": prepared.headers.get("Authorization", "")}


# ---------------------------------------------------------------------------
# Thread splitter
# ---------------------------------------------------------------------------

def _split_thread(content: str) -> List[str]:
    """
    Split a numbered thread draft into individual tweet strings.

    Recognises two common formats:
      - Lines that begin with a thread marker like "1/", "2/", "1.", "2." at
        the very start of the line (optionally followed by a space).
      - A plain string with no thread markers — returned as a single-item list.

    Each returned string is stripped of its leading marker.
    """
    # Match lines starting with a number followed by / or . (e.g. "1/ ", "2. ")
    marker_re = re.compile(r"^\d+[/\.]\s*")

    lines = content.splitlines()
    tweets: List[str] = []
    current_lines: List[str] = []

    for line in lines:
        if marker_re.match(line):
            # Save the previous tweet if there is one
            if current_lines:
                tweets.append("\n".join(current_lines).strip())
                current_lines = []
            # Strip the marker from the start of the new tweet
            current_lines.append(marker_re.sub("", line))
        else:
            current_lines.append(line)

    if current_lines:
        tweets.append("\n".join(current_lines).strip())

    # Filter empty strings that can arise from blank separator lines
    tweets = [t for t in tweets if t]

    # If no markers were found, return the whole content as a single tweet
    return tweets if tweets else [content.strip()]


# ---------------------------------------------------------------------------
# GitHub Release publishing
# ---------------------------------------------------------------------------

async def publish_github_release(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    tag_name: str,
    target_branch: str,
    draft_release: bool,
    prerelease: bool,
    db: AsyncSession,
) -> dict:
    """
    Publish a draft as a GitHub release.

    Returns a dict with keys: success, post_url, post_record_id, error, details.
    Never raises — publishing failures are captured in the returned dict.
    """
    if not settings.github_token:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": "GITHUB_TOKEN is not configured.",
            "details": None,
        }

    # --- Load project and draft ---
    project = await _load_project(project_id, db)
    if project is None:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Project {project_id} not found.",
            "details": None,
        }

    if not project.github_repo:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Project '{project.name}' has no GitHub repo configured.",
            "details": None,
        }

    draft = await _load_draft(draft_id, db)
    if draft is None or draft.project_id != project_id:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Draft {draft_id} not found.",
            "details": None,
        }

    try:
        owner, repo = project.github_repo.split("/", 1)
    except ValueError:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": (
                f"Invalid github_repo format: '{project.github_repo}'. "
                "Expected 'owner/repo'."
            ),
            "details": None,
        }

    # Use the draft title as the release name when available
    release_name = draft.title or tag_name

    payload = {
        "tag_name": tag_name,
        "name": release_name,
        "body": draft.content,
        "target_commitish": target_branch,
        "draft": draft_release,
        "prerelease": prerelease,
    }

    url = f"https://api.github.com/repos/{owner}/{repo}/releases"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=_github_headers())
            response_data = response.json()

            if response.status_code not in (200, 201):
                if response.status_code in (403, 404):
                    error_msg = (
                        "GitHub token lacks permission to create releases. "
                        "Generate a new token with 'repo' scope at "
                        "https://github.com/settings/tokens"
                    )
                else:
                    error_msg = (
                        f"GitHub API error {response.status_code}: "
                        f"{response_data.get('message', 'Unknown error')}"
                    )
                return {
                    "success": False,
                    "post_url": None,
                    "post_record_id": None,
                    "error": error_msg,
                    "details": response_data,
                }

    except httpx.RequestError as exc:
        logger.exception(
            "Network error publishing GitHub release for project=%s draft=%s",
            project_id, draft_id,
        )
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Network error contacting GitHub: {exc}",
            "details": None,
        }

    post_url = response_data.get("html_url")

    # --- Persist record and update draft status ---
    record = await _create_post_record(
        draft_id=draft_id,
        project_id=project_id,
        platform="github_release",
        post_url=post_url,
        db=db,
    )

    draft.status = "published"
    await db.flush()

    logger.info(
        "GitHub release published: project=%s draft=%s tag=%s url=%s",
        project_id, draft_id, tag_name, post_url,
    )

    return {
        "success": True,
        "post_url": post_url,
        "post_record_id": record.id,
        "error": None,
        "details": {
            "release_id": response_data.get("id"),
            "tag_name": response_data.get("tag_name"),
            "name": response_data.get("name"),
            "draft": response_data.get("draft"),
            "prerelease": response_data.get("prerelease"),
            "created_at": response_data.get("created_at"),
            "published_at": response_data.get("published_at"),
        },
    }


# ---------------------------------------------------------------------------
# Twitter / X publishing
# ---------------------------------------------------------------------------

async def _post_tweet(
    text: str,
    reply_to_id: Optional[str],
) -> dict:
    """
    POST a single tweet via Twitter API v2.

    Returns the full API response dict. Raises httpx.HTTPStatusError on
    non-2xx responses so callers can inspect the body.
    """
    body: dict = {"text": text}
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    # Build OAuth 1.0a Authorization header
    try:
        auth_headers = _twitter_headers()
    except ImportError:
        raise RuntimeError(
            "requests and requests_oauthlib must be installed to use Twitter publishing. "
            "Add them to requirements.txt."
        )

    headers = {
        "Content-Type": "application/json",
        **auth_headers,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.twitter.com/2/tweets",
            json=body,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


def _missing_twitter_credentials() -> Optional[str]:
    """Return an error message if any Twitter credential is missing, else None."""
    missing = [
        name
        for name, val in [
            ("TWITTER_API_KEY", settings.twitter_api_key),
            ("TWITTER_API_SECRET", settings.twitter_api_secret),
            ("TWITTER_ACCESS_TOKEN", settings.twitter_access_token),
            ("TWITTER_ACCESS_SECRET", settings.twitter_access_secret),
        ]
        if not val
    ]
    if missing:
        return f"Missing Twitter credentials: {', '.join(missing)}"
    return None


async def publish_tweet(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Publish a draft as a tweet or thread.

    Thread detection:
    - If the content contains numbered markers (1/, 2/, …) it is split into
      individual tweets which are posted as a reply chain.
    - If the content is 280 characters or fewer, it is posted as a single tweet.
    - If the content exceeds 280 characters with no thread markers, it is posted
      as a single tweet anyway — Twitter will truncate server-side; the caller
      should have ensured correct length before calling.

    Returns a dict with keys: success, post_url, post_record_id, error, details.
    Never raises.
    """
    cred_error = _missing_twitter_credentials()
    if cred_error:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": cred_error,
            "details": None,
        }

    draft = await _load_draft(draft_id, db)
    if draft is None or draft.project_id != project_id:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Draft {draft_id} not found.",
            "details": None,
        }

    tweets = _split_thread(draft.content)

    try:
        prev_tweet_id: Optional[str] = None
        posted: List[dict] = []

        for tweet_text in tweets:
            response_data = await _post_tweet(tweet_text, reply_to_id=prev_tweet_id)
            tweet_data = response_data.get("data", {})
            prev_tweet_id = tweet_data.get("id")
            posted.append(tweet_data)

    except RuntimeError as exc:
        # Missing optional dependency
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": str(exc),
            "details": None,
        }
    except httpx.HTTPStatusError as exc:
        body: dict = {}
        try:
            body = exc.response.json()
        except Exception:
            pass
        logger.exception(
            "Twitter API error publishing draft=%s: %s", draft_id, exc
        )
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": (
                f"Twitter API error {exc.response.status_code}: "
                f"{body.get('detail') or body.get('title') or 'Unknown error'}"
            ),
            "details": body,
        }
    except httpx.RequestError as exc:
        logger.exception(
            "Network error publishing tweet for draft=%s", draft_id
        )
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Network error contacting Twitter: {exc}",
            "details": None,
        }

    # The first tweet in the thread is the canonical post URL
    first_tweet_id = posted[0].get("id") if posted else None
    post_url: Optional[str] = None
    if first_tweet_id:
        # Construct the tweet URL; we don't have the username here so we use
        # the generic i/web path which redirects correctly.
        post_url = f"https://twitter.com/i/web/status/{first_tweet_id}"

    record = await _create_post_record(
        draft_id=draft_id,
        project_id=project_id,
        platform="twitter",
        post_url=post_url,
        db=db,
    )

    draft.status = "published"
    await db.flush()

    logger.info(
        "Tweet published: project=%s draft=%s tweets=%d first_id=%s",
        project_id, draft_id, len(posted), first_tweet_id,
    )

    return {
        "success": True,
        "post_url": post_url,
        "post_record_id": record.id,
        "error": None,
        "details": {
            "tweet_count": len(posted),
            "tweets": posted,
        },
    }


# ---------------------------------------------------------------------------
# LinkedIn publishing
# ---------------------------------------------------------------------------

async def publish_linkedin(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Publish a draft as a LinkedIn post using the project owner's stored token.

    Requires the project owner to have completed the OAuth flow
    (GET /linkedin/auth → /linkedin/callback).

    Returns a dict with keys: success, post_url, post_record_id, error, details.
    Never raises.
    """
    # Look up the project owner to fetch their LinkedIn token.
    from sqlalchemy import select
    from app.models.project import Project

    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Project {project_id} not found.",
            "details": None,
        }

    access_token = await linkedin_service.load_token_for_user(project.user_id, db)
    if not access_token:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": (
                "LinkedIn is not connected for this project's owner. "
                "Visit Settings → LinkedIn to authorize your account."
            ),
            "details": None,
        }

    draft = await _load_draft(draft_id, db)
    if draft is None or draft.project_id != project_id:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Draft {draft_id} not found.",
            "details": None,
        }

    # Get the LinkedIn member ID for the author URN.
    person_id = None
    try:
        profile = await linkedin_service.get_profile(access_token)
        person_id = profile.get("id") or profile.get("sub")
    except Exception:
        logger.debug("LinkedIn profile fetch failed", exc_info=True)

    if not person_id:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": (
                "Cannot determine LinkedIn member ID. "
                "Please add 'Sign In with LinkedIn using OpenID Connect' product "
                "to your LinkedIn app at https://developer.linkedin.com — "
                "it's instant approval and grants the profile scope needed."
            ),
            "details": None,
        }

    author_urn = f"urn:li:person:{person_id}"

    # Post to LinkedIn
    try:
        post_data = await linkedin_service.publish_post(
            access_token=access_token,
            author_urn=author_urn,
            text=draft.content,
        )
    except httpx.HTTPStatusError as exc:
        body: dict = {}
        try:
            body = exc.response.json()
        except Exception:
            pass
        logger.exception(
            "LinkedIn API error publishing draft=%s: %s", draft_id, exc
        )
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": (
                f"LinkedIn API error {exc.response.status_code}: "
                f"{body.get('message') or body.get('serviceErrorCode') or 'Unknown error'}"
            ),
            "details": body,
        }
    except httpx.RequestError as exc:
        logger.exception(
            "Network error publishing LinkedIn post for draft=%s", draft_id
        )
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Network error contacting LinkedIn: {exc}",
            "details": None,
        }

    # LinkedIn does not return a direct post URL from the REST Posts API;
    # we store the post URN and link to the user's activity feed as a fallback.
    post_urn = post_data.get("post_urn")
    post_url: Optional[str] = None
    if post_urn:
        # Encode the URN for use in the URL (colons must be percent-encoded)
        encoded_urn = post_urn.replace(":", "%3A")
        post_url = f"https://www.linkedin.com/feed/update/{encoded_urn}/"

    record = await _create_post_record(
        draft_id=draft_id,
        project_id=project_id,
        platform="linkedin",
        post_url=post_url,
        db=db,
    )

    draft.status = "published"
    await db.flush()

    logger.info(
        "LinkedIn post published: project=%s draft=%s urn=%s",
        project_id, draft_id, post_urn,
    )

    return {
        "success": True,
        "post_url": post_url,
        "post_record_id": record.id,
        "error": None,
        "details": {"post_urn": post_urn, "author_urn": author_urn},
    }


# ---------------------------------------------------------------------------
# Dev.to publishing
# ---------------------------------------------------------------------------

async def publish_devto(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Publish a draft as a Dev.to article.

    Uses the Dev.to (Forem) REST API:
      POST https://dev.to/api/articles
      Headers: api-key, Content-Type, User-Agent
      Body: {"article": {"title": ..., "body_markdown": ..., "published": true, "tags": [...]}}

    Returns a dict with keys: success, post_url, post_record_id, error, details.
    Never raises — publishing failures are captured in the returned dict.
    """
    if not settings.devto_api_key:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": "DEVTO_API_KEY is not configured. Set it in Settings > AI & API Keys.",
            "details": None,
        }

    draft = await _load_draft(draft_id, db)
    if draft is None or draft.project_id != project_id:
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Draft {draft_id} not found.",
            "details": None,
        }

    # Extract tags from draft platform or use a generic tag
    tags = []
    if draft.platform:
        tags.append(draft.platform.lower().replace(" ", ""))
    tags.append("projectscribe")
    # Dev.to allows max 4 tags
    tags = tags[:4]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://dev.to/api/articles",
                headers={
                    "api-key": settings.devto_api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "ProjectScribe/1.0",
                },
                json={
                    "article": {
                        "title": draft.title or "Untitled",
                        "body_markdown": draft.content or "",
                        "published": True,
                        "tags": tags,
                    }
                },
            )

        if resp.status_code == 201:
            data = resp.json()
            post_url = data.get("url", "")

            # Mark draft as published
            draft.status = "published"
            await db.flush()

            record = await _create_post_record(
                draft_id=draft_id,
                project_id=project_id,
                platform="devto",
                post_url=post_url,
                db=db,
            )

            return {
                "success": True,
                "post_url": post_url,
                "post_record_id": record.id,
                "error": None,
                "details": {
                    "article_id": data.get("id"),
                    "slug": data.get("slug"),
                    "reading_time_minutes": data.get("reading_time_minutes"),
                },
            }
        else:
            error_body = resp.text[:500]
            logger.warning(
                "publish_devto: API returned %d: %s", resp.status_code, error_body
            )
            return {
                "success": False,
                "post_url": None,
                "post_record_id": None,
                "error": f"Dev.to API returned {resp.status_code}: {error_body[:200]}",
                "details": {"status_code": resp.status_code, "body": error_body},
            }

    except Exception as exc:
        logger.exception("publish_devto: unexpected error")
        return {
            "success": False,
            "post_url": None,
            "post_record_id": None,
            "error": f"Dev.to publishing failed: {exc}",
            "details": None,
        }


# ---------------------------------------------------------------------------
# Hashnode publishing
# ---------------------------------------------------------------------------

async def publish_hashnode(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Publish a draft as a Hashnode blog post via GraphQL API."""
    if not settings.hashnode_api_key:
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": "HASHNODE_API_KEY is not configured. Set it in Settings > AI & API Keys.",
            "details": None,
        }
    if not settings.hashnode_publication_id:
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": "HASHNODE_PUBLICATION_ID is not configured. Set it in Settings > AI & API Keys.",
            "details": None,
        }

    draft = await _load_draft(draft_id, db)
    if draft is None or draft.project_id != project_id:
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": f"Draft {draft_id} not found.", "details": None,
        }

    mutation = """
    mutation ($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          url
          id
          slug
        }
      }
    }
    """

    variables = {
        "input": {
            "publicationId": settings.hashnode_publication_id,
            "title": draft.title or "Untitled",
            "contentMarkdown": draft.content or "",
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://gql.hashnode.com",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": settings.hashnode_api_key,
                },
                json={"query": mutation, "variables": variables},
            )

        data = resp.json()

        if resp.status_code == 200 and "data" in data and data["data"].get("publishPost"):
            post_data = data["data"]["publishPost"]["post"]
            post_url = post_data.get("url", "")

            draft.status = "published"
            await db.flush()

            record = await _create_post_record(
                draft_id=draft_id,
                project_id=project_id,
                platform="hashnode",
                post_url=post_url,
                db=db,
            )

            return {
                "success": True,
                "post_url": post_url,
                "post_record_id": record.id,
                "error": None,
                "details": {
                    "post_id": post_data.get("id"),
                    "slug": post_data.get("slug"),
                },
            }
        else:
            errors = data.get("errors", [])
            error_msg = errors[0].get("message", str(data)) if errors else str(data)
            logger.warning("publish_hashnode: API error: %s", error_msg[:200])
            return {
                "success": False, "post_url": None, "post_record_id": None,
                "error": f"Hashnode API error: {error_msg[:200]}",
                "details": {"response": data},
            }

    except Exception as exc:
        logger.exception("publish_hashnode: unexpected error")
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": f"Hashnode publishing failed: {exc}",
            "details": None,
        }


# ---------------------------------------------------------------------------
# Content-based publishing (for BlogPosts — papers, articles)
# ---------------------------------------------------------------------------
# These functions accept title+content directly instead of loading a Draft.
# They do NOT create a PostRecord because PostRecord.draft_id is a non-nullable
# FK to drafts.id which cannot hold a blog_post_id.
# ---------------------------------------------------------------------------

async def publish_content_to_devto(
    project_id: uuid.UUID,
    title: str,
    content: str,
    source_id: uuid.UUID,
    source_type: str,  # "draft" or "blog_post"
    db: AsyncSession,
) -> dict:
    """Publish any content to Dev.to (used for BlogPost publishing)."""
    if not settings.devto_api_key:
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": "DEVTO_API_KEY is not configured. Set it in Settings > AI & API Keys.",
            "details": None,
        }

    tags = ["projectscribe"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://dev.to/api/articles",
                headers={
                    "api-key": settings.devto_api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "ProjectScribe/1.0",
                },
                json={
                    "article": {
                        "title": title or "Untitled",
                        "body_markdown": content or "",
                        "published": True,
                        "tags": tags,
                    }
                },
            )

        if resp.status_code == 201:
            data = resp.json()
            post_url = data.get("url", "")

            logger.info(
                "publish_content_to_devto: published %s %s -> %s",
                source_type, source_id, post_url,
            )

            return {
                "success": True,
                "post_url": post_url,
                "post_record_id": None,
                "error": None,
                "details": {
                    "article_id": data.get("id"),
                    "slug": data.get("slug"),
                    "reading_time_minutes": data.get("reading_time_minutes"),
                },
            }
        else:
            error_body = resp.text[:500]
            logger.warning(
                "publish_content_to_devto: API returned %d: %s",
                resp.status_code, error_body,
            )
            return {
                "success": False, "post_url": None, "post_record_id": None,
                "error": f"Dev.to API returned {resp.status_code}: {error_body[:200]}",
                "details": {"status_code": resp.status_code, "body": error_body},
            }

    except Exception as exc:
        logger.exception("publish_content_to_devto: unexpected error")
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": f"Dev.to publishing failed: {exc}",
            "details": None,
        }


async def publish_content_to_hashnode(
    project_id: uuid.UUID,
    title: str,
    content: str,
    source_id: uuid.UUID,
    source_type: str,  # "draft" or "blog_post"
    db: AsyncSession,
) -> dict:
    """Publish any content to Hashnode (used for BlogPost publishing)."""
    if not settings.hashnode_api_key:
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": "HASHNODE_API_KEY is not configured. Set it in Settings > AI & API Keys.",
            "details": None,
        }
    if not settings.hashnode_publication_id:
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": "HASHNODE_PUBLICATION_ID is not configured. Set it in Settings > AI & API Keys.",
            "details": None,
        }

    mutation = """
    mutation ($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          url
          id
          slug
        }
      }
    }
    """

    variables = {
        "input": {
            "publicationId": settings.hashnode_publication_id,
            "title": title or "Untitled",
            "contentMarkdown": content or "",
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://gql.hashnode.com",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": settings.hashnode_api_key,
                },
                json={"query": mutation, "variables": variables},
            )

        data = resp.json()

        if resp.status_code == 200 and "data" in data and data["data"].get("publishPost"):
            post_data = data["data"]["publishPost"]["post"]
            post_url = post_data.get("url", "")

            logger.info(
                "publish_content_to_hashnode: published %s %s -> %s",
                source_type, source_id, post_url,
            )

            return {
                "success": True,
                "post_url": post_url,
                "post_record_id": None,
                "error": None,
                "details": {
                    "post_id": post_data.get("id"),
                    "slug": post_data.get("slug"),
                },
            }
        else:
            errors = data.get("errors", [])
            error_msg = errors[0].get("message", str(data)) if errors else str(data)
            logger.warning(
                "publish_content_to_hashnode: API error: %s", error_msg[:200],
            )
            return {
                "success": False, "post_url": None, "post_record_id": None,
                "error": f"Hashnode API error: {error_msg[:200]}",
                "details": {"response": data},
            }

    except Exception as exc:
        logger.exception("publish_content_to_hashnode: unexpected error")
        return {
            "success": False, "post_url": None, "post_record_id": None,
            "error": f"Hashnode publishing failed: {exc}",
            "details": None,
        }
