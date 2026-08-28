"""PyInstaller entry point."""

from __future__ import annotations

import sys

from codex_meter.cli import main


def run() -> int:
    try:
        return main(["app", *sys.argv[1:]])
    except Exception as exc:  # packaged GUI needs a visible failure path
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "Codex Dollar",
                f"启动失败：{type(exc).__name__}\n\n请确认本机存在 ~/.codex/sessions。",
            )
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
