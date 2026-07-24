"""
Native dialogs to capture credentials locally.

Invoked as a subprocess by the MCP server so the operator can add
credentials from the Claude interface without them ever transiting through
the conversation: values go from these windows straight to the OS credential
store.

Usage:  python -m koi_pov_mcp.gui koi <alias> [base_url]
        python -m koi_pov_mcp.gui xsiam <alias>
(legacy: a bare alias as first arg means koi mode)

Exit codes: 0 saved, 2 cancelled, 3 tkinter unavailable, 4 bad usage,
5 invalid input.
"""

from __future__ import annotations

import sys

from . import secrets

TIMEOUT_MS = 180_000  # auto-cancel after 3 minutes


def _run_dialog(build) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("tkinter not available on this Python", file=sys.stderr)
        return 3

    result = {"code": 2}
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid()

    on_save = build(tk, ttk, root, frame, result)

    root.bind("<Return>", on_save)
    root.bind("<Escape>", lambda e=None: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.after(TIMEOUT_MS, root.destroy)
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
    root.geometry(f"+{x}+{y}")
    root.lift()
    root.focus_force()
    root.mainloop()
    return result["code"]


def koi_dialog(alias: str, base_url: str) -> int:
    def build(tk, ttk, root, frame, result):
        root.title(f"koi-pov-mcp: Koi tenant '{alias}'")
        ttk.Label(frame, text=f"Koi API key for tenant '{alias}'",
                  font=("", 10, "bold")).grid(column=0, row=0, sticky="w")
        ttk.Label(frame, text="Stored in the OS credential store. "
                              "Never shared with Claude.").grid(
            column=0, row=1, sticky="w", pady=(0, 8))
        entry = ttk.Entry(frame, show="*", width=52)
        entry.grid(column=0, row=2, sticky="we")
        entry.focus_set()
        status = ttk.Label(frame, text="", foreground="red")
        status.grid(column=0, row=3, sticky="w")

        def on_save(_e=None):
            try:
                secrets.add_tenant(alias, entry.get().strip(), base_url)
            except ValueError as exc:
                status.config(text=str(exc))
                return
            result["code"] = 0
            root.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(column=0, row=4, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=root.destroy).grid(column=0, row=0, padx=(0, 6))
        ttk.Button(buttons, text="Save", command=on_save).grid(column=1, row=0)
        return on_save

    return _run_dialog(build)


def xsiam_dialog(alias: str) -> int:
    def build(tk, ttk, root, frame, result):
        root.title(f"koi-pov-mcp: XSIAM link for '{alias}'")
        ttk.Label(frame, text=f"XSIAM tenant for Koi tenant '{alias}'",
                  font=("", 10, "bold")).grid(column=0, row=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Stored locally (key in the OS credential store). "
                              "Never shared with Claude.").grid(
            column=0, row=1, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="API URL").grid(column=0, row=2, sticky="w")
        url = ttk.Entry(frame, width=52)
        url.insert(0, "https://api-")
        url.grid(column=1, row=2, sticky="we", pady=2)

        ttk.Label(frame, text="API Key ID").grid(column=0, row=3, sticky="w")
        kid = ttk.Entry(frame, width=52)
        kid.grid(column=1, row=3, sticky="we", pady=2)

        ttk.Label(frame, text="API Key").grid(column=0, row=4, sticky="w")
        key = ttk.Entry(frame, show="*", width=52)
        key.grid(column=1, row=4, sticky="we", pady=2)

        advanced = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Advanced API key (hashed auth)",
                        variable=advanced).grid(column=1, row=5, sticky="w", pady=(4, 0))

        status = ttk.Label(frame, text="", foreground="red")
        status.grid(column=0, row=6, columnspan=2, sticky="w")
        url.focus_set()

        def on_save(_e=None):
            try:
                secrets.xsiam_add(
                    alias, url.get().strip(), kid.get().strip(),
                    key.get().strip(), advanced.get(),
                )
            except ValueError as exc:
                status.config(text=str(exc))
                return
            result["code"] = 0
            root.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(column=0, row=7, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=root.destroy).grid(column=0, row=0, padx=(0, 6))
        ttk.Button(buttons, text="Save", command=on_save).grid(column=1, row=0)
        return on_save

    return _run_dialog(build)


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("usage: python -m koi_pov_mcp.gui [koi|xsiam] <alias> [base_url]",
              file=sys.stderr)
        return 4
    if args[0] in ("koi", "xsiam"):
        mode, rest = args[0], args[1:]
    else:  # legacy: bare alias means koi
        mode, rest = "koi", args
    if not rest or not rest[0].strip():
        print("missing alias", file=sys.stderr)
        return 4
    alias = rest[0].strip().lower()
    if mode == "koi":
        return koi_dialog(alias, rest[1].strip() if len(rest) > 1 else "")
    return xsiam_dialog(alias)


if __name__ == "__main__":
    sys.exit(main())
