"""
Tenant credential store: Koi keys and optional linked XSIAM credentials.

Secrets live in the OS credential store when available (Windows Credential
Manager, macOS Keychain, Secret Service on Linux) via `keyring`; fallback is
a 0600-permission JSON file. Non-secret metadata (aliases, URLs, key IDs)
lives in tenants.json. Env vars (KOI_API_KEY[_<ALIAS>]) remain supported for
Koi keys and take precedence.

The store is read at call time: additions apply immediately, no restart.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from platformdirs import user_data_dir

try:
    import keyring
    _HAVE_KEYRING = True
except ImportError:  # pragma: no cover
    _HAVE_KEYRING = False

APP_NAME = "koi-pov-mcp"
SERVICE = "koi-pov-mcp"
KEY_PREFIX = "KOI_API_KEY_"
ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def store_dir() -> Path:
    p = Path(os.environ.get("KOI_POV_WORKDIR") or user_data_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path() -> Path:
    return store_dir() / "tenants.json"


def _load_index() -> dict:
    p = _index_path()
    if p.exists():
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {"tenants": {}, "xsiam": {}}


def _save_index(data: dict) -> None:
    p = _index_path()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    try:
        os.chmod(p, 0o600)
    except OSError:  # Windows: ACLs, chmod is best-effort
        pass


def keyring_available() -> bool:
    if not _HAVE_KEYRING:
        return False
    try:
        keyring.get_password(SERVICE, "__probe__")
        return True
    except Exception:  # noqa: BLE001
        return False


def _put_secret(username: str, secret: str) -> str:
    if keyring_available():
        keyring.set_password(SERVICE, username, secret)
        return "keyring"
    return "file"


def _get_secret(username: str, entry: dict) -> str:
    if entry.get("key_in") == "keyring":
        if not _HAVE_KEYRING:
            return ""
        try:
            return keyring.get_password(SERVICE, username) or ""
        except Exception:  # noqa: BLE001
            return ""
    return entry.get("key", "")


def _del_secret(username: str, entry: dict) -> None:
    if entry.get("key_in") == "keyring" and _HAVE_KEYRING:
        try:
            keyring.delete_password(SERVICE, username)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------- #
# Koi tenants
# ---------------------------------------------------------------------- #


def add_tenant(alias: str, key: str, base_url: str = "") -> str:
    alias = alias.strip().lower()
    if not ALIAS_RE.match(alias):
        raise ValueError(
            f"Invalid alias '{alias}': lowercase letters, digits, '-', '_', "
            "max 40 chars, must start alphanumeric."
        )
    if not key:
        raise ValueError("Empty key.")
    idx = _load_index()
    entry: dict[str, str] = {"base_url": base_url}
    entry["key_in"] = _put_secret(alias, key)
    if entry["key_in"] == "file":
        entry["key"] = key
    idx.setdefault("tenants", {})[alias] = entry
    _save_index(idx)
    return entry["key_in"]


def remove_tenant(alias: str) -> bool:
    alias = alias.strip().lower()
    idx = _load_index()
    entry = idx.get("tenants", {}).pop(alias, None)
    if entry is None:
        return False
    _del_secret(alias, entry)
    idx.get("xsiam", {}).pop(alias, None)
    _save_index(idx)
    return True


def stored_tenants() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    idx = _load_index()
    for alias, entry in idx.get("tenants", {}).items():
        key = _get_secret(alias, entry)
        if key:
            out[alias] = {
                "key": key,
                "base_url": entry.get("base_url", ""),
                "source": "store",
            }
    return out


def all_tenants() -> dict[str, dict[str, str]]:
    """Merged registry: local store first, environment variables override."""
    out = stored_tenants()
    if os.environ.get("KOI_API_KEY"):
        out["default"] = {
            "key": os.environ["KOI_API_KEY"],
            "base_url": os.environ.get("KOI_BASE_URL", ""),
            "source": "env",
        }
    for name, value in os.environ.items():
        if not name.startswith(KEY_PREFIX) or not value:
            continue
        alias = name[len(KEY_PREFIX):].lower()
        if not ALIAS_RE.match(alias):
            continue
        out[alias] = {
            "key": value,
            "base_url": os.environ.get(f"KOI_BASE_URL_{alias.upper()}", "")
            or os.environ.get("KOI_BASE_URL", ""),
            "source": "env",
        }
    return out


# ---------------------------------------------------------------------- #
# XSIAM links (optional, one per Koi tenant alias)
# ---------------------------------------------------------------------- #


def xsiam_add(alias: str, api_url: str, key_id: str, key: str,
              advanced: bool = False) -> str:
    alias = alias.strip().lower()
    if not ALIAS_RE.match(alias):
        raise ValueError(f"Invalid alias '{alias}'.")
    if not (api_url and key_id and key):
        raise ValueError("API URL, key ID and key are all required.")
    if not api_url.lower().startswith("https://"):
        raise ValueError("API URL must start with https://")
    idx = _load_index()
    entry: dict = {
        "api_url": api_url.rstrip("/"),
        "key_id": str(key_id).strip(),
        "advanced": bool(advanced),
    }
    entry["key_in"] = _put_secret(f"xsiam:{alias}", key)
    if entry["key_in"] == "file":
        entry["key"] = key
    idx.setdefault("xsiam", {})[alias] = entry
    _save_index(idx)
    return entry["key_in"]


def xsiam_get(alias: str) -> dict | None:
    alias = alias.strip().lower()
    entry = _load_index().get("xsiam", {}).get(alias)
    if not entry:
        return None
    key = _get_secret(f"xsiam:{alias}", entry)
    if not key:
        return None
    return {
        "api_url": entry.get("api_url", ""),
        "key_id": entry.get("key_id", ""),
        "advanced": bool(entry.get("advanced")),
        "key": key,
    }


def xsiam_remove(alias: str) -> bool:
    alias = alias.strip().lower()
    idx = _load_index()
    entry = idx.get("xsiam", {}).pop(alias, None)
    if entry is None:
        return False
    _del_secret(f"xsiam:{alias}", entry)
    _save_index(idx)
    return True


def xsiam_list() -> dict[str, dict]:
    """alias -> {api_url, key_id, advanced} (never the key)."""
    out = {}
    for alias, entry in _load_index().get("xsiam", {}).items():
        out[alias] = {
            "api_url": entry.get("api_url", ""),
            "key_id": entry.get("key_id", ""),
            "advanced": bool(entry.get("advanced")),
        }
    return out
