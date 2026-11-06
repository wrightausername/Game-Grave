"""Compatibility entrypoint for the currently authorized Mods-only scope check.

Baseline d7c12e7 contains the completed Games, Overview and Ready Room work.
All nine pages outside Mods and their shared controls remain protected.
"""
if __package__:
    from .mods_scope_smoke import main
else:
    from mods_scope_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
