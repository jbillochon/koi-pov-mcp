"""
Tenant credential store.

Keys live in the OS credential store when available (Windows Credential
Manager, macOS Keychain, Secret Service on Linux) via `keyring`. When no
backend is available (typical on headless Linux), keys fall back to a
0600-permission JSON file next to the tenant index.

Environment variables (KOI_API_KEY, KOI_API_KEY_<ALIAS>) remain supported and
take precedence, so existing setups keep working.

The store is read at call time, not at server start: a tenant added with
`koi-pov-mcp tenants add <alias>` is usable immediately, no Claude restart.
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
    return {"tenants": {}}


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
    except Exception:  # noqa: BLE001 - any backend failure means "no"
        return False


def add_tenant(alias: str, key: str, base_url: str = "") -> str:
    """Store a tenant key. Returns where it went: 'keyring' or 'file'."""
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
    if keyring_available():
        keyring.set_password(SERVICE, alias, key)
        entry["key_in"] = "keyring"
    else:
        entry["key"] = key
        entry["key_in"] = "file"
    idx["tenants"][alias] = entry
    _save_index(idx)
    return entry["key_in"]


def remove_tenant(alias: str) -> bool:
    alias = alias.strip().lower()
    idx = _load_index()
    entry = idx["tenants"].pop(alias, None)
    if entry is None:
        return False
    if entry.get("key_in") == "keyring" and _HAVE_KEYRING:
        try:
            keyring.delete_password(SERVICE, alias)
        except Exception:  # noqa: BLE001 - index removal already done
            pass
    _save_index(idx)
    return True


def stored_tenants() -> dict[str, dict[str, str]]:
    """alias -> {key, base_url, source='store'} from the local store."""
    out: dict[str, dict[str, str]] = {}
    idx = _load_index()
    for alias, entry in idx.get("tenants", {}).items():
        if entry.get("key_in") == "keyring":
            key = ""
            if _HAVE_KEYRING:
                try:
                    key = keyring.get_password(SERVICE, alias) or ""
                except Exception:  # noqa: BLE001
                    key = ""
        else:
            key = entry.get("key", "")
        if key:
            out[alias] = {
                "key": key,
                "base_url": entry.get("base_url", ""),
                "source": "store",
            }
    return out


def all_tenants() -> dict[str, dict[str, str]]:
    """Merged registry: local store first, environment variables override.

    Env precedence keeps existing installs (keys in the Claude config env
    block) working unchanged.
    """
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
