"""Simple Fernet encryption for API keys stored in the database.

The encryption key is auto-generated on first use and stored at
/app/backend_data/fernet.key (inside the Docker volume so it persists
across container restarts).
"""
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_KEY_PATH = Path(os.environ.get("FERNET_KEY_PATH", "/app/backend_data/fernet.key"))
_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    if _KEY_PATH.exists():
        key = _KEY_PATH.read_bytes().strip()
        logger.info("encryption: loaded Fernet key from %s", _KEY_PATH)
    else:
        key = Fernet.generate_key()
        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _KEY_PATH.write_bytes(key)
        logger.info("encryption: generated new Fernet key at %s", _KEY_PATH)

    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as a UTF-8 string."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token back to a plaintext string."""
    return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
