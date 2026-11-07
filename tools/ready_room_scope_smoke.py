"""Check that Ready Room changes preserve all twelve other tabs."""
if __package__:
    from .ready_room_tab_lock import main
else:
    from ready_room_tab_lock import main

if __name__ == "__main__":
    raise SystemExit(main())
