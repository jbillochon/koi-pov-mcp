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

Two things this module learned the hard way, both of which made the tool
report failure while the browser page was in fact open:

* ``sys.executable`` is NOT python when the server was started through the
  console-script wrapper, which is exactly how MCP hosts launch it. It is
  ``koi-pov-mcp.exe``, and re-invoking that with ``-m`` hits the CLI's
  argument parser instead of the capture page. Resolve a real interpreter.
* Reading exactly one line and giving up on anything unexpected is too
  fragile: any preamble on stdout, or a slow first spawn under endpoint
  security, loses a URL that was printed correctly. Read until the timeout,
  and when the page is still alive say so instead of calling it a failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

URL_WAIT_SEC = 30

# Keep references so the child processes are not garbage collected while the
# operator is still filling the form.
_RUNNING: list[subprocess.Popen] = []


def interpreter() -> str:
    """Return a real Python interpreter, not a console-script wrapper.

    In a venv the interpreter sits next to the wrapper in Scripts/ (Windows)
    or bin/ (POSIX), so the sibling lookup covers every layout this ships in.
    """
    exe = Path(sys.executable)
    if exe.stem.lower().startswith("python"):
        return str(exe)

    base = getattr(sys, "_base_executable", "")
    if base and Path(base).stem.lower().startswith("python"):
        return base

    for name in ("python.exe", "pythonw.exe", "python3", "python"):
        candidate = exe.parent / name
        if candidate.exists():
            return str(candidate)

    return sys.executable


def _pump(proc: subprocess.Popen, out: dict, deadline: float) -> None:
    """Collect stdout until the URL shows up or the deadline passes."""
    try:
        while time.monotonic() < deadline:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    return
                continue
            out.setdefault("log", []).append(line.rstrip())
            if line.startswith("URL "):
                out["url"] = line[4:].strip()
                return
    except Exception as exc:  # noqa: BLE001
        out["read_error"] = f"{type(exc).__name__}: {exc}"


def launch(mode: str, alias: str, base_url: str = "") -> dict:
    """Start the capture page. Returns {url, error} without waiting for input."""
    cmd = [interpreter(), "-m", "koi_pov_mcp.gui", mode, alias]
    if base_url:
        cmd.append(base_url)

    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "bufsize": 1,
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
    deadline = time.monotonic() + URL_WAIT_SEC
    reader = threading.Thread(target=_pump, args=(proc, out, deadline), daemon=True)
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
        if not detail:
            detail = "; ".join(out.get("log", [])) or f"exited ({proc.returncode})"
        return {"url": "", "error": detail}

    # Still alive and serving: the browser tab has almost certainly opened even
    # though the URL never reached us. Saying "it failed" here is what sent an
    # operator to the terminal fallback while the page sat open in front of
    # them, so say what is actually true instead.
    reason = out.get("read_error") or "no URL was reported within the timeout"
    return {
        "url": "",
        "error": (
            f"the capture page is running but {reason}. A browser tab may "
            "already be open; check for it before falling back"
        ),
    }
