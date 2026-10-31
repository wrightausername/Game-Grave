"""Explicit opt-in Qt preview. Legacy Tk remains default until acceptance."""
from __future__ import annotations
import sys


def main() -> int:
    if "--ui-preview" not in sys.argv:
        print("Crimson Command is an opt-in engineering preview. "
              "Run python -m gg_desktop --ui-preview", file=sys.stderr)
        return 2
    try:
        from gg_desktop.app import main as start
    except ImportError as exc:
        print("PySide6 is required for the optional desktop preview. "
              "Install dependencies from ui-preview-requirements.txt.", file=sys.stderr)
        return 2
    return start()


if __name__ == "__main__":
    raise SystemExit(main())
