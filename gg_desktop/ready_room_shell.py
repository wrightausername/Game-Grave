"""Compatibility import for Ready Room's native page.

Ready Room uses the existing app shell and normal Qt widget sizing. Its former
whole-window graphics canvas and automatic zoom are deliberately removed.
"""
from gg_desktop.ready_room import ReadyRoomPage

__all__ = ["ReadyRoomPage"]
