"""MCP tools for the optional XSIAM cross-referencing; registered onto the
shared FastMCP instance (see server.py bottom)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import secrets
from .client import KoiClient
from .xsiam import XsiamClient, XsiamError, correlate


def register(mcp, resolve_tenant, tenant_dir):
    @mcp.tool()
    def xsiam_tenant_add(tenant: str = "default") -> str:
        """Link an XSIAM tenant to a Koi tenant, from the Claude interface.
        Opens a native dialog on the operator's machine with three fields:
        API URL (the tenant's api- FQDN), API Key ID, and the API key (masked),
        plus an 'advanced key' checkbox. Everything is stored locally (key in
        the OS credential store); nothing transits through the conversation.

        Use when the operator wants XSIAM cross-referencing on a tenant that
        has no XSIAM link yet (koi_tenants shows xsiam_linked). Connectivity
        is tested automatically on success. Never ask for XSIAM credentials
        in chat."""
        resolved = resolve_tenant(tenant)
        if isinstance(resolved, dict):
            return resolved.get("error", "unknown error")
        alias, _ = resolved

        python = sys.executable
        if os.name == "nt":
            pythonw = Path(python).with_name("pythonw.exe")
            if pythonw.exists():
                python = str(pythonw)
        try:
            proc = subprocess.run(
                [python, "-m", "koi_pov_mcp.gui", "xsiam", alias],
                capture_output=True, text=True, timeout=260,
            )
        except subprocess.TimeoutExpired:
            return "Dialog timed out with no input. Nothing was saved."

        if proc.returncode == 0:
            return f"XSIAM tenant linked to '{alias}'. " + _xsiam_ping(alias)
        if proc.returncode == 2:
            return "Cancelled by the operator. Nothing was saved."
        if proc.returncode == 3:
            return (
                "No graphical dialog available (tkinter missing). Fallback: "
                f"run in a terminal: koi-pov-mcp xsiam add {alias}"
            )
        detail = (proc.stderr or "").strip()
        return f"Dialog failed (exit {proc.returncode}). {detail or 'Nothing was saved.'}"

    @mcp.tool()
    def xsiam_correlate(tenant: str = "default", days: int = 30) -> dict:
        """Cross-reference one Koi tenant with its linked XSIAM tenant:
        agent coverage overlap (Koi-managed vs XSIAM-managed hosts) and XSIAM
        incidents from the last N days landing on Koi-known hosts. Facts only;
        saves <tenant>/xsiam_correlation.json, then pov_report_json includes
        it under 'xsiam'. Use when the operator accepts the XSIAM option of
        the deliverable workflow. If no XSIAM tenant is linked, offer
        xsiam_tenant_add. Coverage gaps (koi_only / xsiam_only) are deployment
        facts for the operator; present them carefully, never as customer
        blame."""
        resolved = resolve_tenant(tenant)
        if isinstance(resolved, dict):
            return resolved
        alias, koi_creds = resolved

        x = secrets.xsiam_get(alias)
        if not x:
            return {
                "tenant": alias,
                "error": (
                    "No XSIAM tenant linked to this Koi tenant. "
                    "Use xsiam_tenant_add to link one (native dialog)."
                ),
            }
        try:
            payload = correlate(
                KoiClient(api_key=koi_creds["key"],
                          base_url=koi_creds["base_url"] or None),
                XsiamClient(x["api_url"], x["key_id"], x["key"],
                            advanced=x.get("advanced", False)),
                days=days,
            )
        except XsiamError as exc:
            return {"tenant": alias, "error": f"XSIAM: {exc}"}

        payload["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = tenant_dir(alias) / "xsiam_correlation.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return {"tenant": alias, "correlation_path": str(out), **payload}

    def _xsiam_ping(alias: str) -> str:
        x = secrets.xsiam_get(alias)
        if not x:
            return "No XSIAM credentials found after save (unexpected)."
        try:
            XsiamClient(x["api_url"], x["key_id"], x["key"],
                        advanced=x.get("advanced", False)).ping()
        except XsiamError as exc:
            return f"XSIAM connectivity check failed: {exc}"
        return "XSIAM connectivity check: OK."

    return xsiam_tenant_add, xsiam_correlate
