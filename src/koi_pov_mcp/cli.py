"""
Command-line interface.

`koi-pov-mcp` with no arguments (or `serve`) runs the MCP server, which is
what Claude Desktop invokes. Everything else is tenant management:

    koi-pov-mcp tenants add acme        # prompts for the key, input hidden
    koi-pov-mcp tenants list
    koi-pov-mcp tenants test acme       # ping the Koi API with that key
    koi-pov-mcp tenants remove acme

Keys never appear in argv (visible in the process list) and never transit
through a Claude conversation.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from . import secrets
from .client import KoiAPIError, KoiAuthError, KoiClient


def _cmd_add(args: argparse.Namespace) -> int:
    alias = args.alias.strip().lower()
    try:
        key = getpass.getpass(f"Koi API key for tenant '{alias}' (input hidden): ").strip()
        where = secrets.add_tenant(alias, key, args.base_url)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    location = (
        "OS credential store" if where == "keyring"
        else f"local file ({secrets.store_dir() / 'tenants.json'}, permissions restricted)"
    )
    print(f"Tenant '{alias}' saved in the {location}.")
    print("Available immediately in Claude, no restart needed.")
    if args.test:
        return _cmd_test(argparse.Namespace(alias=alias))
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    registry = secrets.all_tenants()
    if not registry:
        print("No tenants configured. Add one with: koi-pov-mcp tenants add <alias>")
        return 0
    width = max(len(a) for a in registry)
    print(f"{'ALIAS'.ljust(width)}  SOURCE   BASE URL")
    for alias in sorted(registry):
        info = registry[alias]
        print(f"{alias.ljust(width)}  {info['source']:<7}  {info['base_url'] or '(default)'}")
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
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


def _cmd_remove(args: argparse.Namespace) -> int:
    alias = args.alias.strip().lower()
    if secrets.remove_tenant(alias):
        print(f"Tenant '{alias}' removed from the store.")
        return 0
    print(f"Nothing removed: '{alias}' is not in the store "
          "(env-configured tenants are managed in the Claude config).",
          file=sys.stderr)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="koi-pov-mcp",
        description="Koi PoV MCP server and tenant key management",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the MCP server on stdio (default)")

    tenants = sub.add_parser("tenants", help="manage tenant API keys")
    tsub = tenants.add_subparsers(dest="tcmd", required=True)

    p_add = tsub.add_parser("add", help="add or update a tenant (prompts for the key)")
    p_add.add_argument("alias", help="tenant alias, e.g. acme")
    p_add.add_argument("--base-url", default="", help="override the Koi API base URL")
    p_add.add_argument("--test", action="store_true", help="ping the API after saving")
    p_add.set_defaults(func=_cmd_add)

    tsub.add_parser("list", help="list configured tenants").set_defaults(func=_cmd_list)

    p_test = tsub.add_parser("test", help="ping the Koi API for one tenant")
    p_test.add_argument("alias")
    p_test.set_defaults(func=_cmd_test)

    p_rm = tsub.add_parser("remove", help="remove a tenant from the store")
    p_rm.add_argument("alias")
    p_rm.set_defaults(func=_cmd_remove)

    args = parser.parse_args()
    if args.cmd in (None, "serve"):
        from .server import mcp
        mcp.run()
        return
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
