"""Compatibility entrypoint for the authorized Old Files-only scope check.

Baseline cc64c75 contains the completed Mods, Games, Overview and Ready Room.
All nine pages outside Old Files and their shared controls remain protected.
"""
if __package__:
    from .old_files_scope_smoke import main
else:
    from old_files_scope_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
