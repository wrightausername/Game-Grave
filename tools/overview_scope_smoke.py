"""Compatibility entrypoint preserving Overview during the Games task.

The expanded scope check compares Overview pixels at three window sizes and
all nine pages outside Games against the approved 5f5d57d baseline.
"""
if __package__:
    from .games_scope_smoke import main
else:
    from games_scope_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
