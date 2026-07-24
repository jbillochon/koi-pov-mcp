"""
Local credential capture.

Secrets are entered in a page served on 127.0.0.1 by a short-lived HTTP
server and written straight to the OS credential store. The value never
transits through the Claude conversation.

Why a browser page and not a native window: when Claude Desktop spawns the
MCP server, a tkinter window gets created but is not reliably surfaced to
the user's desktop (it can sit invisible until the timeout). A browser tab
is surfaced reliably, and the URL can always be relayed to the operator as a
fallback. Tk remains available with --tk.

Usage:  python -m koi_pov_mcp.gui koi <alias> [base_url] [--tk]
        python -m koi_pov_mcp.gui xsiam <alias> [--tk]

The first stdout line is 'URL <address>' so the caller can relay it.
Exit codes: 0 saved, 2 cancelled/timeout, 3 no UI available, 4 bad usage.
"""

from __future__ import annotations

import html
import secrets as pysecrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import secrets

TIMEOUT_SEC = 300

CSS = (
    "body{font-family:system-ui,Segoe UI,Helvetica,Arial,sans-serif;"
    "background:#f4f5f7;margin:0;padding:40px}"
    ".card{max-width:520px;margin:0 auto;background:#fff;border-radius:10px;"
    "padding:28px 32px;box-shadow:0 2px 12px rgba(0,0,0,.10)}"
    "h1{font-size:19px;margin:0 0 6px}p.sub{color:#555;font-size:13px;margin:0 0 20px}"
    "label{display:block;font-size:13px;font-weight:600;margin:14px 0 4px}"
    "input[type=text],input[type=password]{width:100%;box-sizing:border-box;"
    "padding:9px 10px;border:1px solid #ccd;border-radius:6px;font-size:14px}"
    ".row{display:flex;align-items:center;gap:8px;margin-top:14px;font-size:13px}"
    "button{margin-top:22px;width:100%;padding:11px;border:0;border-radius:6px;"
    "background:#1f6feb;color:#fff;font-size:15px;font-weight:600;cursor:pointer}"
    ".err{color:#b00020;font-size:13px;margin-top:12px}"
    ".ok{color:#0a7d33;font-weight:600}"
)


def _page(body: str) -> bytes:
    return (
        "<!doctype html><meta charset=utf-8><title>koi-pov-mcp</title>"
        f"<style>{CSS}</style><div class=card>{body}</div>"
    ).encode("utf-8")


def _koi_form(alias: str, error: str = "") -> bytes:
    err = f"<p class=err>{html.escape(error)}</p>" if error else ""
    return _page(
        f"<h1>Koi API key for tenant '{html.escape(alias)}'</h1>"
        "<p class=sub>Stored in your OS credential store. Never shared with Claude.</p>"
        "<form method=post><label>API key</label>"
        "<input type=password name=key autofocus autocomplete=off>"
        "<button type=submit>Save</button>" + err + "</form>"
    )


def _xsiam_form(alias: str, error: str = "") -> bytes:
    err = f"<p class=err>{html.escape(error)}</p>" if error else ""
    return _page(
        f"<h1>XSIAM tenant for Koi tenant '{html.escape(alias)}'</h1>"
        "<p class=sub>Stored locally, key in your OS credential store. "
        "Never shared with Claude.</p>"
        "<form method=post>"
        "<label>API URL</label>"
        "<input type=text name=api_url value='https://api-' autocomplete=off>"
        "<label>API Key ID</label><input type=text name=key_id autocomplete=off>"
        "<label>API Key</label><input type=password name=key autocomplete=off>"
        "<div class=row><input type=checkbox name=advanced id=adv>"
        "<label for=adv style='margin:0;font-weight:400'>"
        "Advanced API key (hashed auth)</label></div>"
        "<button type=submit>Save</button>" + err + "</form>"
    )


def _done() -> bytes:
    return _page(
        "<h1 class=ok>Saved.</h1>"
        "<p class=sub>You can close this tab and go back to Claude.</p>"
    )


def serve(mode: str, alias: str, base_url: str) -> int:
    token = pysecrets.token_urlsafe(24)
    state = {"code": 2}

    class Handler(BaseHTTPRequestHandler):
        def _authorised(self) -> bool:
            qs = parse_qs(urlparse(self.path).query)
            return pysecrets.compare_digest((qs.get("t") or [""])[0], token)

        def _send(self, body: bytes, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorised():
                self._send(_page("<h1>Invalid or expired link.</h1>"), 403)
                return
            self._send(_koi_form(alias) if mode == "koi" else _xsiam_form(alias))

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorised():
                self._send(_page("<h1>Invalid or expired link.</h1>"), 403)
                return
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8"))

            def field(name: str) -> str:
                return (form.get(name) or [""])[0].strip()

            try:
                if mode == "koi":
                    secrets.add_tenant(alias, field("key"), base_url)
                else:
                    secrets.xsiam_add(
                        alias, field("api_url"), field("key_id"), field("key"),
                        bool(form.get("advanced")),
                    )
            except ValueError as exc:
                self._send(
                    _koi_form(alias, str(exc)) if mode == "koi"
                    else _xsiam_form(alias, str(exc))
                )
                return
            state["code"] = 0
            self._send(_done())
            threading.Thread(target=httpd.shutdown, daemon=True).start()

        def log_message(self, *_args) -> None:  # keep stderr clean
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{httpd.server_port}/?t={token}"
    # First stdout line: the caller relays this to the operator.
    print(f"URL {url}", flush=True)

    threading.Timer(
        TIMEOUT_SEC,
        lambda: threading.Thread(target=httpd.shutdown, daemon=True).start(),
    ).start()
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - the URL is relayed anyway
        pass
    httpd.serve_forever()
    httpd.server_close()
    return state["code"]


def serve_tk(mode: str, alias: str, base_url: str) -> int:
    """Optional native-window mode (--tk). Kept for environments where the
    window is reliably surfaced."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("tkinter not available", file=sys.stderr)
        return 3

    result = {"code": 2}
    root = tk.Tk()
    root.title(f"koi-pov-mcp: {alias}")
    root.attributes("-topmost", True)
    frame = ttk.Frame(root, padding=16)
    frame.grid()
    entries: dict[str, object] = {}

    if mode == "koi":
        ttk.Label(frame, text=f"Koi API key for '{alias}'",
                  font=("", 10, "bold")).grid(column=0, row=0, columnspan=2, sticky="w")
        e = ttk.Entry(frame, show="*", width=52)
        e.grid(column=0, row=1, columnspan=2, pady=6)
        e.focus_set()
        entries["key"] = e
    else:
        ttk.Label(frame, text=f"XSIAM tenant for '{alias}'",
                  font=("", 10, "bold")).grid(column=0, row=0, columnspan=2, sticky="w")
        for i, (label, name, hide) in enumerate(
            [("API URL", "api_url", False), ("API Key ID", "key_id", False),
             ("API Key", "key", True)], start=1
        ):
            ttk.Label(frame, text=label).grid(column=0, row=i, sticky="w")
            e = ttk.Entry(frame, width=46, show="*" if hide else "")
            if name == "api_url":
                e.insert(0, "https://api-")
            e.grid(column=1, row=i, pady=3)
            entries[name] = e
        adv = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Advanced API key", variable=adv).grid(
            column=1, row=4, sticky="w")
        entries["advanced"] = adv

    status = ttk.Label(frame, text="", foreground="red")
    status.grid(column=0, row=6, columnspan=2, sticky="w")

    def save(_e=None):
        try:
            if mode == "koi":
                secrets.add_tenant(alias, entries["key"].get().strip(), base_url)
            else:
                secrets.xsiam_add(
                    alias, entries["api_url"].get().strip(),
                    entries["key_id"].get().strip(), entries["key"].get().strip(),
                    entries["advanced"].get(),
                )
        except ValueError as exc:
            status.config(text=str(exc))
            return
        result["code"] = 0
        root.destroy()

    ttk.Button(frame, text="Save", command=save).grid(
        column=1, row=7, sticky="e", pady=(10, 0))
    root.bind("<Return>", save)
    root.bind("<Escape>", lambda e=None: root.destroy())
    root.after(TIMEOUT_SEC * 1000, root.destroy)
    root.lift()
    root.focus_force()
    root.mainloop()
    return result["code"]


def main() -> int:
    args = list(sys.argv[1:])
    use_tk = "--tk" in args
    args = [a for a in args if a != "--tk"]
    if not args:
        print("usage: python -m koi_pov_mcp.gui [koi|xsiam] <alias> [base_url] [--tk]",
              file=sys.stderr)
        return 4
    mode, rest = (args[0], args[1:]) if args[0] in ("koi", "xsiam") else ("koi", args)
    if not rest or not rest[0].strip():
        print("missing alias", file=sys.stderr)
        return 4
    alias = rest[0].strip().lower()
    base_url = rest[1].strip() if len(rest) > 1 else ""
    if use_tk:
        return serve_tk(mode, alias, base_url)
    return serve(mode, alias, base_url)


if __name__ == "__main__":
    sys.exit(main())
