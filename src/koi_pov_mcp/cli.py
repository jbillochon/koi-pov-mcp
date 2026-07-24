"""
Command-line interface.

`koi-pov-mcp` with no arguments (or `serve`) runs the MCP server. Tenant
management (keys prompted with hidden input, never in argv, never in chat):

    koi-pov-mcp tenants add acme [--test]     koi-pov-mcp xsiam add acme [--advanced]
    koi-pov-mcp tenants list                  koi-pov-mcp xsiam list
    koi-pov-mcp tenants test acme             koi-pov-mcp xsiam test acme
    koi-pov-mcp tenants remove acme           koi-pov-mcp xsiam remove acme
"""

from __future__ import annotations

import argparse
import getpass
import sys

from . import secrets
from .client import KoiAPIError, KoiAuthError, KoiClient


def _cmd_add(args) -> int:
    alias = args.alias.strip().lower()
    try:
        key = getpass.getpass(f"Koi API key for tenant '{alias}' (input hidden): ").strip()
        where = secrets.add_tenant(alias, key, args.base_url)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    location = ("OS credential store" if where == "keyring"
                else f"local file ({secrets.store_dir() / 'tenants.json'}, restricted)")
    print(f"Tenant '{alias}' saved in the {location}.")
    print("Available immediately in Claude, no restart needed.")
    if args.test:
        return _cmd_test(args)
    return 0


def _cmd_list(_args) -> int:
    registry = secrets.all_tenants()
    xsiam = secrets.xsiam_list()
    if not registry:
        print("No tenants configured. Add one with: koi-pov-mcp tenants add <alias>")
        return 0
    width = max(len(a) for a in registry)
    print(f"{'ALIAS'.ljust(width)}  SOURCE   XSIAM  BASE URL")
    for alias in sorted(registry):
        info = registry[alias]
        linked = "yes" if alias in xsiam else "no"
        print(f"{alias.ljust(width)}  {info['source']:<7}  {linked:<5}  "
              f"{info['base_url'] or '(default)'}")
    return 0


def _cmd_test(args) -> int:
    alias = args.alias.strip().lower()
    registry = secrets.all_tenants()
    if alias not in registry:
        print(f"ERROR: unknown tenant '{alias}'. Known: {sorted(registry) or 'none'}",
              file=sys.stderr)
        return 1
    info = registry[alias]
    try:
        KoiClient(api_key=info["key"], base_url=info["base_url"] or None).ping()
    except KoiAuthError:
        print(f"AUTH FAILED for '{alias}': key rejected (401).", file=sys.stderr)
        return 1
    except KoiAPIError as exc:
        print(f"API ERROR for '{alias}': {exc}", file=sys.stderr)
        return 1
    print(f"OK: tenant '{alias}' authenticated against the Koi API.")
    return 0


def _cmd_remove(args) -> int:
    alias = args.alias.strip().lower()
    if secrets.remove_tenant(alias):
        print(f"Tenant '{alias}' removed from the store (XSIAM link included).")
        return 0
    print(f"Nothing removed: '{alias}' is not in the store.", file=sys.stderr)
    return 1


def _cmd_xsiam_add(args) -> int:
    alias = args.alias.strip().lower()
    api_url = input("XSIAM API URL (https://api-...): ").strip()
    key_id = input("XSIAM API Key ID: ").strip()
    key = getpass.getpass("XSIAM API key (input hidden): ").strip()
    try:
        secrets.xsiam_add(alias, api_url, key_id, key, args.advanced)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"XSIAM tenant linked to '{alias}'. Available immediately.")
    if args.test:
        return _cmd_xsiam_test(args)
    return 0


def _cmd_xsiam_list(_args) -> int:
    linked = secrets.xsiam_list()
    if not linked:
        print("No XSIAM tenants linked.")
        return 0
    for alias in sorted(linked):
        e = linked[alias]
        kind = "advanced" if e["advanced"] else "standard"
        print(f"{alias}: {e['api_url']} (key id {e['key_id']}, {kind} key)")
    return 0


def _cmd_xsiam_test(args) -> int:
    from .xsiam import XsiamClient, XsiamError
    alias = args.alias.strip().lower()
    x = secrets.xsiam_get(alias)
    if not x:
        print(f"ERROR: no XSIAM tenant linked to '{alias}'.", file=sys.stderr)
        return 1
    try:
        XsiamClient(x["api_url"], x["key_id"], x["key"], advanced=x["advanced"]).ping()
    except XsiamError as exc:
        print(f"XSIAM ERROR for '{alias}': {exc}", file=sys.stderr)
        return 1
    print(f"OK: XSIAM tenant linked to '{alias}' is reachable and authenticated.")
    return 0


def _cmd_xsiam_remove(args) -> int:
    alias = args.alias.strip().lower()
    if secrets.xsiam_remove(alias):
        print(f"XSIAM link removed from '{alias}'.")
        return 0
    print(f"Nothing removed: no XSIAM link on '{alias}'.", file=sys.stderr)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="koi-pov-mcp",
        description="Koi PoV MCP server, tenant and XSIAM credential management",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the MCP server on stdio (default)")

    tenants = sub.add_parser("tenants", help="manage Koi tenant API keys")
    tsub = tenants.add_subparsers(dest="tcmd", required=True)
    p = tsub.add_parser("add"); p.add_argument("alias")
    p.add_argument("--base-url", default=""); p.add_argument("--test", action="store_true")
    p.set_defaults(func=_cmd_add)
    tsub.add_parser("list").set_defaults(func=_cmd_list)
    p = tsub.add_parser("test"); p.add_argument("alias"); p.set_defaults(func=_cmd_test)
    p = tsub.add_parser("remove"); p.add_argument("alias"); p.set_defaults(func=_cmd_remove)

    xsiam = sub.add_parser("xsiam", help="manage linked XSIAM tenants")
    xsub = xsiam.add_subparsers(dest="xcmd", required=True)
    p = xsub.add_parser("add"); p.add_argument("alias")
    p.add_argument("--advanced", action="store_true",
                   help="the key is an Advanced API key (hashed auth)")
    p.add_argument("--test", action="store_true")
    p.set_defaults(func=_cmd_xsiam_add)
    xsub.add_parser("list").set_defaults(func=_cmd_xsiam_list)
    p = xsub.add_parser("test"); p.add_argument("alias"); p.set_defaults(func=_cmd_xsiam_test)
    p = xsub.add_parser("remove"); p.add_argument("alias"); p.set_defaults(func=_cmd_xsiam_remove)

    args = parser.parse_args()
    if args.cmd in (None, "serve"):
        from .server import mcp
        mcp.run()
        return
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
