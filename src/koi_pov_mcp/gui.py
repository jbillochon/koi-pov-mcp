"""
Native dialog to capture a tenant API key locally.

Invoked as a subprocess by the MCP server (`koi_tenant_add` tool) so the
operator can add a tenant from the Claude interface without the key ever
transiting through the conversation: the key goes from this window straight
to the OS credential store.

Exit codes: 0 saved, 2 cancelled, 3 tkinter unavailable, 4 bad usage,
5 invalid alias/key.
"""

from __future__ import annotations

import sys

from . import secrets

TIMEOUT_MS = 180_000  # auto-cancel after 3 minutes


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("usage: python -m koi_pov_mcp.gui <alias> [base_url]", file=sys.stderr)
        return 4
    alias = sys.argv[1].strip().lower()
    base_url = sys.argv[2].strip() if len(sys.argv) > 2 else ""

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("tkinter not available on this Python", file=sys.stderr)
        return 3

    result: dict[str, int] = {"code": 2}  # cancelled by default

    root = tk.Tk()
    root.title(f"koi-pov-mcp: tenant '{alias}'")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=16)
    frame.grid()

    ttk.Label(
        frame,
        text=f"Koi API key for tenant '{alias}'",
        font=("", 10, "bold"),
    ).grid(column=0, row=0, columnspan=2, sticky="w")
    ttk.Label(
        frame,
        text="Stored in the OS credential store. Never shared with Claude.",
    ).grid(column=0, row=1, columnspan=2, sticky="w", pady=(0, 8))

    entry = ttk.Entry(frame, show="*", width=52)
    entry.grid(column=0, row=2, columnspan=2, sticky="we")
    entry.focus_set()

    status = ttk.Label(frame, text="", foreground="red")
    status.grid(column=0, row=3, columnspan=2, sticky="w")

    def on_save(_event=None) -> None:
        key = entry.get().strip()
        try:
            secrets.add_tenant(alias, key, base_url)
        except ValueError as exc:
            status.config(text=str(exc))
            return
        result["code"] = 0
        root.destroy()

    def on_cancel(_event=None) -> None:
        result["code"] = 2
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(column=0, row=4, columnspan=2, sticky="e", pady=(10, 0))
    ttk.Button(buttons, text="Cancel", command=on_cancel).grid(column=0, row=0, padx=(0, 6))
    ttk.Button(buttons, text="Save", command=on_save).grid(column=1, row=0)

    root.bind("<Return>", on_save)
    root.bind("<Escape>", on_cancel)
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.after(TIMEOUT_MS, on_cancel)

    # Center on screen and bring to front
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
    root.geometry(f"+{x}+{y}")
    root.lift()
    root.focus_force()

    root.mainloop()
    return result["code"]


if __name__ == "__main__":
    sys.exit(main())
