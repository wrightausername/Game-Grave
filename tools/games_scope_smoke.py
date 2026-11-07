"""Protect all twelve other tabs during Games work."""
if __package__:
    from .games_tab_lock import main
else:
    from games_tab_lock import main

if __name__ == '__main__':
    raise SystemExit(main())
