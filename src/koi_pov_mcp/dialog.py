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

Three things this module learned the hard way, each of which made the tool
report failure while the browser page was in fact open:

* ``sys.executable`` is NOT python when the server was started through the
  console-script wrapper, which is exactly how MCP hosts launch it. It is
  ``koi-pov-mcp.exe``, and re-invoking that with ``-m`` hits the CLI's
  argument parser instead of the capture page. Resolve a real interpreter.
* Reading exactly one line and giving up on anything unexpected is too
  fragile: any preamble, or a slow first spawn under endpoint security, loses
  a URL that was printed correctly.
* An anonymous pipe is not a dependable channel here. Driven from a terminal
  the child's stdout arrives in milliseconds; spawned from inside an MCP host
  on an EDR-managed workstation it does not, and the URL was lost while the
  page sat open in front of the operator. The child now writes to a file on
  disk and this module polls it. A file also survives the call: when the URL
  still does not arrive, its path goes in the error message so the operator
  can read the URL themselves instead of being told it failed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

URL_WAIT_SEC = 30
POLL_SEC = 0.15

# Keep references so the child processes are not garbage collected while the
# operator is still filling the form.
_RUNNING: list[subprocess.Popen] = []

_URL_RE = re.compile(r"^URL\s+(\S+)", re.MULTILINE)


def interpreter() -> str:
    """Return a real Python interpreter that can import this package.

    Order matters. The venv's own interpreter sits next to the console-script
    wrapper, so the sibling lookup comes first: ``sys._base_executable``
    points at the base installation, where this package is not installed, and
    trying it first resolves to an interpreter that cannot run the capture
    page at all.
    """
    exe = Path(sys.executable)
    if exe.stem.lower().startswith("python"):
        return str(exe)

    for name in ("python.exe", "pythonw.exe", "python3", "python"):
        candidate = exe.parent / name
        if candidate.exists():
            return str(candidate)

    base = getattr(sys, "_base_executable", "")
    if base and Path(base).stem.lower().startswith("python"):
        return base

    return sys.executable


def capture_log(mode: str, alias: str) -> Path:
    """Where the capture page's output is collected for this launch."""
    safe = re.sub(r"[^a-z0-9_-]+", "", str(alias).lower())[:40] or "tenant"
    return Path(tempfile.gettempdir()) / f"koi-pov-capture-{mode}-{safe}.log"


def _url_from(path: Path) -> str:
    try:
        match = _URL_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""
    return match.group(1) if match else ""


def launch(mode: str, alias: str, base_url: str = "") -> dict:
    """Start the capture page. Returns {url, error} without waiting for input."""
    cmd = [interpreter(), "-m", "koi_pov_mcp.gui", mode, alias]
    if base_url:
        cmd.append(base_url)

    log_path = capture_log(mode, alias)
    try:
        log_path.unlink()
    except OSError:
        pass

    try:
        handle = open(log_path, "w", encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"url": "", "error": f"could not open the capture log: {exc}"}

    kwargs: dict = {"stdout": handle, "stderr": subprocess.STDOUT, "text": True}
    if os.name == "nt":  # no console flash
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        handle.close()
        return {"url": "", "error": f"could not start the capture page: {exc}"}

    _RUNNING.append(proc)
    _RUNNING[:] = [p for p in _RUNNING if p.poll() is None]

    deadline = time.monotonic() + URL_WAIT_SEC
    while time.monotonic() < deadline:
        url = _url_from(log_path)
        if url:
            return {"url": url, "error": ""}
        if proc.poll() is not None:
            break
        time.sleep(POLL_SEC)

    url = _url_from(log_path)  # one last look; it may have landed on the way out
    if url:
        return {"url": url, "error": ""}

    tail = ""
    try:
        tail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-400:]
    except OSError:
        pass

    if proc.poll() is not None:
        return {"url": "", "error": tail or f"capture page exited ({proc.returncode})"}

    # Still alive and serving. The browser tab has almost certainly opened; the
    # URL simply has not reached us yet. Saying "it failed" here is what sent an
    # operator to the terminal fallback while the page waited in front of them.
    detail = f" Output so far: {tail}" if tail else ""
    return {
        "url": "",
        "error": (
            "the capture page is running but has not reported its URL yet. A "
            "browser tab is probably already open; if not, the address is in "
            f"{log_path}.{detail}"
        ),
    }
