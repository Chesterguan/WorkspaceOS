"""Read / write capability config overrides + merge over the manifest.

The merge rule is "DB overlays manifest":

  effective = { **manifest_config, **db_overlay }

So manifest config provides defaults + structural hints; the DB
overlay carries the user-filled credentials. Fields the user hasn't
touched stay at manifest defaults.

Encryption uses the existing Fernet key (same one app_settings uses
for API key storage). Plain text never leaves this service except
when:
  - The frontend GETs config for the settings UI (and we redact
    fields marked sensitive before sending).
  - The capability runner consults effective config at run time.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Set

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.capability_settings import CapabilitySetting
from app.services.encryption import decrypt, encrypt

logger = logging.getLogger(__name__)


# Field names treated as sensitive — values are masked when the frontend
# fetches config for display. The UI keeps the actual value in the
# encrypted DB; we just don't echo it back over the wire.
SENSITIVE_KEYS: Set[str] = {
    "api_key", "api_token", "token", "access_token", "password",
    "secret", "client_secret", "sidecar_token",
}


async def get_overlay(extension_id: str, capability_name: str) -> Dict[str, Any]:
    """Return the user-supplied config overlay for this capability.

    Empty dict if nothing has been saved yet. Plain values (decrypted).
    """
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            select(CapabilitySetting).where(
                CapabilitySetting.extension_id == extension_id,
                CapabilitySetting.capability_name == capability_name,
            )
        )
        record = row.scalar_one_or_none()
        if record is None:
            return {}
        try:
            return json.loads(decrypt(record.encrypted_config))
        except Exception:
            logger.exception("capability_settings: failed to decrypt %s/%s",
                             extension_id, capability_name)
            return {}


async def set_overlay(
    extension_id: str,
    capability_name: str,
    overlay: Dict[str, Any],
) -> None:
    """Upsert the overlay. Encrypts the JSON blob before write."""
    payload = encrypt(json.dumps(overlay))
    async with AsyncSessionLocal() as db:
        stmt = (
            pg_insert(CapabilitySetting)
            .values(
                extension_id=extension_id,
                capability_name=capability_name,
                encrypted_config=payload,
            )
            .on_conflict_do_update(
                index_elements=[
                    CapabilitySetting.extension_id,
                    CapabilitySetting.capability_name,
                ],
                set_={"encrypted_config": payload},
            )
        )
        await db.execute(stmt)
        await db.commit()


def effective_config(
    manifest_config: Dict[str, Any],
    overlay: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge — overlay wins. Caller is responsible for passing both."""
    return {**(manifest_config or {}), **(overlay or {})}


def redact_for_display(config: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive values for transport to the frontend.

    `api_key: "abc123…"` becomes `api_key: "***"`. The UI can still see
    whether the field is set (truthy) vs empty (falsy) — useful for
    form prefill — without ever pulling the plaintext back.
    """
    out: Dict[str, Any] = {}
    for k, v in (config or {}).items():
        if k in SENSITIVE_KEYS and v:
            out[k] = "***"
        else:
            out[k] = v
    return out
