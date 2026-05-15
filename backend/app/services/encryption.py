"""Simple Fernet encryption for API keys stored in the database.

The encryption key is auto-generated on first use and stored at
/app/data/fernet.key. /app/data IS the mounted Docker volume
(`backend_data:/app/data` in docker-compose.yml), so the key
persists across container restarts AND recreates.

History: the default used to be /app/backend_data/fernet.key, which
was NEVER mounted — every `docker compose up --force-recreate`
generated a fresh key and silently invalidated every DB-encrypted
secret (API keys saved via Settings would "work" then mysteriously
revert to .env after a rebuild). Pointing at the actual persisted
volume fixes that. Override with FERNET_KEY_PATH if you mount the
volume elsewhere.
"""
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_KEY_PATH = Path(os.environ.get("FERNET_KEY_PATH", "/app/data/fernet.key"))
_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    if _KEY_PATH.exists():
        key = _KEY_PATH.read_bytes().strip()
        logger.info("encryption: loaded existing Fernet key from %s", _KEY_PATH)
    else:
        key = Fernet.generate_key()
        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _KEY_PATH.write_bytes(key)
        os.chmod(_KEY_PATH, 0o600)
        logger.warning(
            "encryption: NO EXISTING KEY FOUND — generating new Fernet key at %s. "
            "Previously encrypted values will be UNREADABLE.",
            _KEY_PATH,
        )

    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as a UTF-8 string."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token back to a plaintext string."""
    return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
