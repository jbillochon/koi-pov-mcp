"""
Launch the local credential-capture page as a subprocess and relay its URL.

The URL is printed by the child on its first stdout line before it starts
waiting, so the MCP tool can hand it to the operator immediately. That way a
browser that fails to open automatically is never a dead end: the operator
can click the link.
"""

from __future__ import annotations

import os
import subprocess
import sys

URL_WAIT_SEC = 15


def launch(mode: str, alias: str, base_url: str = "", timeout: int = 320) -> dict:
    """Run the capture page. Returns {code, url, stderr}.

    code: 0 saved, 2 cancelled/timeout, 3 no UI available, 4 bad usage,
    other = failure (see stderr).
    """
    cmd = [sys.executable, "-m", "koi_pov_mcp.gui", mode, alias]
    if base_url:
        cmd.append(base_url)

    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":  # no console flash, pipes still work
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        return {"code": 5, "url": "", "stderr": f"could not start the capture page: {exc}"}

    url = ""
    try:
        first = proc.stdout.readline() if proc.stdout else ""
        if first.startswith("URL "):
            url = first[4:].strip()
    except Exception:  # noqa: BLE001
        pass

    try:
        _, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"code": 2, "url": url, "stderr": "timed out"}

    return {"code": proc.returncode, "url": url, "stderr": (err or "").strip()}


def describe(result: dict, alias: str, what: str, cli_hint: str) -> str:
    """Turn a launch() result into an operator-facing message."""
    code = result["code"]
    if code == 0:
        return ""
    if code == 2:
        base = f"No {what} was submitted (the page timed out or was closed)."
        if result["url"]:
            base += (
                f" If no browser tab opened, the operator can open this link"
                f" manually while the page is running: {result['url']}"
            )
        return base + f" Terminal fallback: {cli_hint}"
    if code == 3:
        return f"No local UI available. Terminal fallback: {cli_hint}"
    detail = result["stderr"] or "no detail"
    return f"Capture page failed (exit {code}): {detail}. Terminal fallback: {cli_hint}"
