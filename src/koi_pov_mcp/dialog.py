"""
Launch the local credential-capture page as a background subprocess.

The call returns as soon as the page reports its URL (well under a second),
it does not wait for the operator to fill the form. Blocking would be wrong
twice over: it freezes the conversation, and MCP hosts abandon a tool call
after a few minutes, so a slow human would lose the result even after
submitting correctly.

The page keeps running in the background until it is submitted or expires;
the secret is written by that process straight to the OS credential store.
The caller relays the URL and verifies afterwards with a ping.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

URL_WAIT_SEC = 10

# Keep references so the child processes are not garbage collected while the
# operator is still filling the form.
_RUNNING: list[subprocess.Popen] = []


def _read_first_line(proc: subprocess.Popen, out: dict) -> None:
    try:
        line = proc.stdout.readline() if proc.stdout else ""
        if line.startswith("URL "):
            out["url"] = line[4:].strip()
    except Exception:  # noqa: BLE001
        pass


def launch(mode: str, alias: str, base_url: str = "") -> dict:
    """Start the capture page. Returns {url, error} without waiting for input."""
    cmd = [sys.executable, "-m", "koi_pov_mcp.gui", mode, alias]
    if base_url:
        cmd.append(base_url)

    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":  # no console flash; pipes still work
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        return {"url": "", "error": f"could not start the capture page: {exc}"}

    _RUNNING.append(proc)
    _RUNNING[:] = [p for p in _RUNNING if p.poll() is None]

    out: dict = {}
    reader = threading.Thread(target=_read_first_line, args=(proc, out), daemon=True)
    reader.start()
    reader.join(URL_WAIT_SEC)

    url = out.get("url", "")
    if url:
        return {"url": url, "error": ""}

    if proc.poll() is not None:  # died before reporting a URL
        detail = ""
        try:
            detail = (proc.stderr.read() or "").strip() if proc.stderr else ""
        except Exception:  # noqa: BLE001
            pass
        return {"url": "", "error": detail or f"capture page exited ({proc.returncode})"}

    return {"url": "", "error": "the capture page started but reported no URL"}
