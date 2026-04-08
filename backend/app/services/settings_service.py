"""
Settings service: CRUD for encrypted API keys stored in the database.

Keys are Fernet-encrypted at rest. The service provides:
  - get_all_keys() -> dict of key names with masked values
  - get_key_value(key) -> decrypted value
  - set_key(key, value) -> encrypt and store (upsert)
  - delete_key(key) -> remove from DB
  - load_db_keys_into_settings() -> overlay DB values onto the runtime Settings object
"""
import logging
from typing import Dict, List, Optional

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSetting
from app.services.encryption import encrypt, decrypt
from app.config import settings

logger = logging.getLogger(__name__)

# Map of recognized DB key names to Settings attribute names
SETTINGS_KEY_MAP: Dict[str, str] = {
    "gemini_api_key": "gemini_api_key",
    "openai_api_key": "openai_api_key",
    "anthropic_api_key": "anthropic_api_key",
    "github_token": "github_token",
    "api_secret_key": "api_secret_key",
    "linkedin_client_id": "linkedin_client_id",
    "linkedin_client_secret": "linkedin_client_secret",
    "devto_api_key": "devto_api_key",
    "hashnode_api_key": "hashnode_api_key",
    "hashnode_publication_id": "hashnode_publication_id",
    "google_drive_credentials": "google_drive_credentials",
    "notion_api_key": "notion_api_key",
}


def _mask_value(value: str) -> str:
    """Mask a secret value for display: first 4 + '...' + last 3.

    If the value is shorter than 10 chars, return a fixed mask.
    """
    if len(value) < 10:
        return "\u2022\u2022\u2022\u2022\u2022\u2022"
    return value[:4] + "..." + value[-3:]


async def get_all_keys(db: AsyncSession) -> List[Dict]:
    """Return all stored keys with masked values.

    Each entry: {"key": "gemini_api_key", "masked_value": "AIza...xyz",
                 "updated_at": datetime}.
    """
    result = await db.execute(select(AppSetting))
    rows = result.scalars().all()

    keys = []
    for row in rows:
        try:
            plaintext = decrypt(row.value)
            masked = _mask_value(plaintext)
        except Exception:
            masked = "\u2022\u2022\u2022\u2022\u2022\u2022"
        keys.append({
            "key": row.key,
            "masked_value": masked,
            "updated_at": row.updated_at,
        })
    return keys


async def get_key_value(key: str, db: AsyncSession) -> Optional[str]:
    """Decrypt and return a single key's value. Returns None if not found."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return decrypt(row.value)


async def set_key(key: str, value: str, db: AsyncSession) -> None:
    """Encrypt the value and upsert into app_settings table."""
    encrypted = encrypt(value)

    result = await db.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.value = encrypted
    else:
        db.add(AppSetting(key=key, value=encrypted))

    await db.flush()


async def delete_key(key: str, db: AsyncSession) -> bool:
    """Delete a key from the table and restore the .env default at runtime.

    Returns True if found and deleted.
    """
    result = await db.execute(
        sa_delete(AppSetting).where(AppSetting.key == key)
    )
    deleted = result.rowcount > 0

    # Restore the .env default by re-reading from a fresh Settings instance
    if deleted:
        settings_attr = SETTINGS_KEY_MAP.get(key)
        if settings_attr:
            from app.config import Settings
            fresh = Settings()
            env_value = getattr(fresh, settings_attr, "")
            setattr(settings, settings_attr, env_value)
            logger.info("Restored '%s' to .env default", key)

    return deleted


async def load_db_keys_into_settings(db: AsyncSession) -> int:
    """Load all keys from DB, decrypt them, and overlay onto runtime settings.

    Only overrides if the DB value is non-empty.
    Returns count of keys successfully loaded.
    """
    result = await db.execute(select(AppSetting))
    rows = result.scalars().all()

    loaded = 0
    for row in rows:
        settings_attr = SETTINGS_KEY_MAP.get(row.key)
        if settings_attr is None:
            continue
        try:
            plaintext = decrypt(row.value)
        except Exception:
            logger.warning("Failed to decrypt DB key '%s' — skipping", row.key)
            continue
        if not plaintext:
            continue
        setattr(settings, settings_attr, plaintext)
        loaded += 1

    return loaded
