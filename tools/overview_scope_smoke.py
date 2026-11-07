"""Protect Ready Room and the other eleven tabs during Overview work."""
if __package__:
    from .overview_tab_lock import main
else:
    from overview_tab_lock import main

if __name__ == "__main__":
    raise SystemExit(main())
