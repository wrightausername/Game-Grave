"""Compatibility entrypoint for the approved Overview + Ready Room scope check.

Overview functionality was explicitly authorized after Ready Room. The expanded
check preserves the approved Overview pixels and all ten pages, and verifies
that shared styles, application behavior and cleanup backends are unchanged.
"""
if __package__:
    from .overview_scope_smoke import main
else:
    from overview_scope_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
