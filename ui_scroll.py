"""M4 page-wheel ownership: nested lists keep their own scrolling.

Pure UI routing only. No filesystem access or user actions.
"""
from __future__ import annotations


def page_wheel_allowed(found, page, canvas, nested_scroll_types) -> bool:
    widget = found
    visited = set()
    while widget is not None and id(widget) not in visited:
        visited.add(id(widget))
        if isinstance(widget, nested_scroll_types):
            return False
        if widget is page or widget is canvas:
            return True
        widget = getattr(widget, "master", None)
    return False
