"""M4 scroll ownership and small-screen navigation regression checks."""
import unittest
from unittest.mock import Mock

from ui_scroll import page_wheel_allowed
from ui import GameGraveApp


class DummyWidget:
    def __init__(self, master=None):
        self.master = master


class NestedList(DummyWidget):
    pass


class FakeScrollCanvas:
    def __init__(self, height=200, total=850):
        self.height = height
        self.total = total
        self.calls = []
    def bbox(self, _name):
        return (0, 0, 400, self.total)
    def winfo_height(self):
        return self.height
    def yview_scroll(self, n, unit):
        self.calls.append((n, unit))


class FakeApp:
    _scroll_page_on_wheel = GameGraveApp._scroll_page_on_wheel
    def __init__(self):
        self.content_canvas = FakeScrollCanvas()
        self.content = DummyWidget()
        self.target = DummyWidget(self.content)
    def winfo_containing(self, _x, _y):
        return self.target


class PageScrollTests(unittest.TestCase):
    def test_nested_treeview_owns_its_wheel(self):
        page = DummyWidget()
        table = NestedList(page)
        cell = DummyWidget(table)
        self.assertFalse(page_wheel_allowed(cell, page, None, (NestedList,)))
        self.assertTrue(page_wheel_allowed(DummyWidget(page), page, None, (NestedList,)))
        self.assertFalse(page_wheel_allowed(DummyWidget(None), page, None, (NestedList,)))

    def test_chained_parent_cycle_never_hangs(self):
        one = DummyWidget()
        two = DummyWidget(one)
        one.master = two
        self.assertFalse(page_wheel_allowed(one, DummyWidget(), None, (NestedList,)))

    def test_page_wheel_moves_only_for_overflowing_page(self):
        page = FakeApp()
        event = Mock(x_root=50, y_root=50, delta=-120)
        self.assertEqual(page._scroll_page_on_wheel(event), "break")
        self.assertEqual(page.content_canvas.calls, [(3, "units")])
        page.content_canvas.total = 150
        self.assertIsNone(page._scroll_page_on_wheel(event))
        self.assertEqual(page.content_canvas.calls, [(3, "units")])

    def test_wheel_outside_current_page_does_not_scroll(self):
        page = FakeApp()
        page.target = DummyWidget()
        event = Mock(x_root=500, y_root=500, delta=120)
        self.assertIsNone(page._scroll_page_on_wheel(event))
        self.assertFalse(page.content_canvas.calls)


if __name__ == "__main__":
    unittest.main()
