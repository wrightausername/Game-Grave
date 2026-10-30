"""Choose a Windows UI viewport that does not open off the primary display.

Layout fitting does not guarantee every panel is accessible at all sizes.
High-DPI, smaller screens and screen-reader functionality need native QA.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowBounds:
    width: int
    height: int
    min_width: int
    min_height: int
    left: int
    top: int


def initial_window_bounds(screen_width: int, screen_height: int) -> WindowBounds:
    if (not isinstance(screen_width, int) or isinstance(screen_width, bool)
            or not isinstance(screen_height, int) or isinstance(screen_height, bool)
            or screen_width <= 0 or screen_height <= 0):
        raise ValueError("Screen dimensions must be positive integers.")
    # Leave a safety margin for taskbar/window decorations. The user is
    # still able to resize the window and use Windows' normal navigation.
    x_margin = min(72, max(0, screen_width // 14))
    y_margin = min(110, max(0, screen_height // 8))
    width = min(1290, max(1, screen_width - x_margin))
    height = min(820, max(1, screen_height - y_margin))
    return WindowBounds(
        width=width, height=height,
        min_width=min(990, width), min_height=min(660, height),
        left=max(0, (screen_width - width) // 2),
        top=max(0, (screen_height - height) // 2),
    )
