"""Compatibility entrypoint for the latest authorized Games scope check.

The current check protects the completed Overview and Ready Room, every other
page outside Games, the shared shell, styles, artwork and cleanup engines.
"""
if __package__:
    from .games_scope_smoke import main
else:
    from games_scope_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
