#!/usr/bin/env python3
"""
ProjectScribe Outlook Bridge — runs on the user's Mac, queries Outlook
for Mac via AppleScript, POSTs the items into the ProjectScribe backend
at /skills/local-ingest/items.

Runs without any pip dependencies — stdlib only. Installable via
`install.sh` which sets up a launchd job to fire this script every
30 minutes.

Config is read from ~/.projectscribe-bridge.json:
{
  "api_base":      "http://localhost:8989/api/v1",
  "api_key":       "dev-secret-key",
  "access_token":  "<JWT from /auth/login>",
  "refresh_token": "<JWT refresh>"
}

Failure modes handled:
  * Outlook Mac not running / not installed → log + exit 0 (so launchd
    doesn't retry-storm; next tick will try again).
  * osascript timeout → log + exit 0.
  * Backend 401 (token expired) → refresh via /auth/refresh, retry once,
    log if still failing.
  * Backend 5xx / network error → log + exit 0.

Log location: ~/Library/Logs/projectscribe-bridge.log
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths + config
# ---------------------------------------------------------------------------

HOME = Path.home()
CONFIG_PATH = HOME / ".projectscribe-bridge.json"
LOG_PATH = HOME / "Library" / "Logs" / "projectscribe-bridge.log"
APPLESCRIPT_PATH = Path(__file__).resolve().parent / "sync.applescript"

OSASCRIPT_TIMEOUT_SEC = 180
HTTP_TIMEOUT_SEC = 60
BATCH_SIZE = 50  # cap per POST — keeps payloads under the 200-item server cap


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("projectscribe.bridge")
    logger.setLevel(logging.INFO)
    # Avoid duplicate handlers if run repeatedly in the same process
    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH)
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        )
        logger.addHandler(fh)
        # Also emit to stderr for `--verbose` runs / launchd log capture
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(sh)
    return logger


log = _setup_logging()


# ---------------------------------------------------------------------------
# Config load / persist
# ---------------------------------------------------------------------------

def load_config() -> Dict[str, str]:
    if not CONFIG_PATH.exists():
        log.error("Config file %s missing — run install.sh first", CONFIG_PATH)
        sys.exit(1)
    try:
        with CONFIG_PATH.open("r") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Config file %s is unreadable: %s", CONFIG_PATH, exc)
        sys.exit(1)


def persist_tokens(
    cfg: Dict[str, str], access: str, refresh: Optional[str]
) -> None:
    """Persist refreshed tokens atomically. 0600 so other users can't read."""
    cfg["access_token"] = access
    if refresh:
        cfg["refresh_token"] = refresh
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w") as fh:
        json.dump(cfg, fh, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, CONFIG_PATH)


# ---------------------------------------------------------------------------
# AppleScript runner
# ---------------------------------------------------------------------------

def run_applescript() -> List[Dict[str, Any]]:
    """Run sync.applescript and parse its NDJSON output.
    Returns [] on any failure — failure modes are logged, never raised,
    so the bridge exits cleanly and launchd fires again next tick."""
    if not APPLESCRIPT_PATH.exists():
        log.error("AppleScript not found at %s", APPLESCRIPT_PATH)
        return []
    try:
        result = subprocess.run(
            ["osascript", str(APPLESCRIPT_PATH)],
            capture_output=True,
            text=True,
            timeout=OSASCRIPT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        log.warning("osascript timed out after %ds", OSASCRIPT_TIMEOUT_SEC)
        return []
    except FileNotFoundError:
        log.error("osascript not on PATH — are you on macOS?")
        return []

    if result.returncode != 0:
        log.warning(
            "osascript exited rc=%d. stderr=%s",
            result.returncode, result.stderr.strip()[:500],
        )
        return []

    items: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(result.stdout.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            log.warning("line %d: malformed JSON (%s): %s", line_no, exc, line[:120])
    log.info("AppleScript produced %d items (stderr len=%d)", len(items), len(result.stderr))
    return items


# ---------------------------------------------------------------------------
# HTTP — POST + refresh-on-401
# ---------------------------------------------------------------------------

def _post_batch(
    cfg: Dict[str, str], items: List[Dict[str, Any]]
) -> Tuple[int, Optional[Dict[str, Any]]]:
    url = cfg["api_base"].rstrip("/") + "/skills/local-ingest/items"
    body = json.dumps({"items": items}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": cfg["api_key"],
            "Authorization": f"Bearer {cfg['access_token']}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except urllib.error.URLError as exc:
        log.error("POST failed (network): %s", exc)
        return 0, None


def _try_refresh_token(cfg: Dict[str, str]) -> bool:
    refresh = cfg.get("refresh_token")
    if not refresh:
        return False
    url = cfg["api_base"].rstrip("/") + "/auth/refresh"
    body = json.dumps({"refresh_token": refresh}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": cfg["api_key"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.error("refresh failed: %s", exc)
        return False
    new_access = payload.get("access_token")
    new_refresh = payload.get("refresh_token")
    if not new_access:
        log.error("refresh response missing access_token: %s", payload)
        return False
    persist_tokens(cfg, new_access, new_refresh)
    log.info("refreshed access token")
    return True


def post_items(cfg: Dict[str, str], items: List[Dict[str, Any]]) -> bool:
    """Send items in batches. Returns True if every batch was accepted."""
    if not items:
        log.info("nothing to post")
        return True

    all_ok = True
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        status, payload = _post_batch(cfg, batch)
        if status == 401:
            if _try_refresh_token(cfg):
                status, payload = _post_batch(cfg, batch)
        if status == 200 and isinstance(payload, dict):
            log.info(
                "batch %d-%d: fetched=%s created=%s skipped=%s inbox=%s",
                start, start + len(batch),
                payload.get("fetched"), payload.get("created"),
                payload.get("skipped"), payload.get("inbox"),
            )
        else:
            all_ok = False
            log.error("batch %d-%d: POST failed (status=%s)", start, start + len(batch), status)
    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = load_config()
    required = {"api_base", "api_key", "access_token"}
    missing = required - set(cfg)
    if missing:
        log.error("config missing keys: %s", sorted(missing))
        return 1

    items = run_applescript()
    post_items(cfg, items)
    # Always return 0 so launchd doesn't treat transient failures as crashes
    # and apply exponential backoff. Real failure signal is in the log.
    return 0


if __name__ == "__main__":
    sys.exit(main())
