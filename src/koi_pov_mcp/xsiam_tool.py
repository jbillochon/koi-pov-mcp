"""MCP tools for the optional XSIAM cross-referencing; registered onto the
shared FastMCP instance (see server.py bottom)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import dialog, secrets
from .client import KoiClient
from .xsiam import XsiamClient, XsiamError, correlate


def register(mcp, resolve_tenant, tenant_dir):
    @mcp.tool()
    def xsiam_tenant_add(tenant: str = "default") -> str:
        """Link an XSIAM tenant to a Koi tenant, from the Claude interface.

        Opens a credential page in the operator's browser with three fields:
        API URL (the tenant's api- FQDN), API Key ID, and the API key
        (masked), plus an 'advanced key' checkbox for hashed authentication.
        Everything is stored locally (key in the OS credential store);
        nothing transits through the conversation.

        Returns immediately with the page URL: it does NOT wait for the
        operator. Relay the URL verbatim (their browser may not have opened
        by itself), say the page expires in 5 minutes, and wait for them to
        confirm they saved it. Only then verify with xsiam_status_check via
        koi_tenants (xsiam_linked) or xsiam_correlate. Never claim the link
        exists before that.
        """
        resolved = resolve_tenant(tenant)
        if isinstance(resolved, dict):
            return resolved.get("error", "unknown error")
        alias, _ = resolved

        result = dialog.launch("xsiam", alias)
        cli = f"koi-pov-mcp xsiam add {alias} --test"
        if result["error"]:
            return (
                f"Could not open the credential page: {result['error']}. "
                f"Terminal fallback: {cli}"
            )
        return (
            f"XSIAM credential page opened for tenant '{alias}'. "
            f"If no browser tab appeared, open this link: {result['url']} "
            "(expires in 5 minutes). Fields: API URL, API Key ID, API key, "
            "and tick 'Advanced API key' if it is an advanced key. "
            "Nothing is saved until it is submitted."
        )

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
        blame, and never imply causality between a Koi finding and an XSIAM
        incident: co-presence on a host is co-presence."""
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
                    "Use xsiam_tenant_add to link one."
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

    return xsiam_tenant_add, xsiam_correlate
