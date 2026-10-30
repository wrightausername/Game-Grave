"""M4 narrow-screen sidebar and keyboard focus visibility fixtures.

No Game Grave root window, filesystem scan, or deletion is performed.
"""
import unittest
from types import SimpleNamespace

from ui import GameGraveApp


class FakeNavCanvas:
    def __init__(self, content=920, viewport=350):
        self.full=content
        self.height=viewport
        self.start=0
        self.scrolled=[]
        self.positions=[]
    def update_idletasks(self): pass
    def canvasy(self, _offset): return self.start
    def winfo_height(self): return self.height
    def bbox(self, _value): return (0, 0, 190, self.full)
    def yview_moveto(self, ratio):
        self.positions.append(ratio)
        self.start=ratio*self.full
    def yview_scroll(self, offset, unit):
        self.scrolled.append((offset,unit))


class FakeButton:
    def __init__(self, y, h):
        self.y=y
        self.h=h
    def winfo_y(self): return self.y
    def winfo_height(self): return self.h


class FakeFrame:
    def __init__(self, master=None, height=920):
        self.master=master
        self.height=height
    def winfo_height(self): return self.height


class SidebarTests(unittest.TestCase):
    def test_short_screen_reveals_selected_keyboard_page(self):
        app=SimpleNamespace(
            nav_canvas=FakeNavCanvas(),
            nav_list=FakeFrame(),
            nav_buttons={"Settings":FakeButton(y=800,h=55)})
        GameGraveApp._scroll_navigation_to(app,"Settings")
        self.assertEqual(len(app.nav_canvas.positions),1)
        self.assertGreater(app.nav_canvas.positions[0],0)
        self.assertLessEqual(app.nav_canvas.positions[0],1)

    def test_visible_nav_item_does_not_move_sidebar(self):
        app=SimpleNamespace(
            nav_canvas=FakeNavCanvas(),
            nav_list=FakeFrame(),
            nav_buttons={"Overview":FakeButton(y=10,h=45)})
        GameGraveApp._scroll_navigation_to(app,"Overview")
        self.assertFalse(app.nav_canvas.positions)

    def test_sidebar_wheel_scrolls_nav_without_scrolling_page(self):
        class FakeApp:
            def __init__(self):
                self.nav_canvas=FakeNavCanvas()
                self.nav_list=FakeFrame()
                self.content=FakeFrame()
                self.content_canvas=FakeNavCanvas()
                self.hover=FakeFrame(master=self.nav_list)
            def winfo_containing(self,_x,_y): return self.hover
        app=FakeApp()
        event=SimpleNamespace(x_root=100,y_root=150,delta=-120)
        self.assertEqual(GameGraveApp._scroll_page_on_wheel(app,event),"break")
        self.assertEqual(app.nav_canvas.scrolled,[(3,"units")])
        self.assertEqual(app.content_canvas.scrolled,[])

    def test_short_sidebar_does_not_scroll_when_all_buttons_fit(self):
        class FakeApp:
            def __init__(self):
                self.nav_canvas=FakeNavCanvas(content=200,viewport=400)
                self.nav_list=FakeFrame()
                self.content=FakeFrame()
                self.content_canvas=FakeNavCanvas()
                self.hover=FakeFrame(master=self.nav_list)
            def winfo_containing(self,_x,_y): return self.hover
        app=FakeApp()
        event=SimpleNamespace(x_root=100,y_root=150,delta=-120)
        self.assertIsNone(GameGraveApp._scroll_page_on_wheel(app,event))
        self.assertEqual(app.nav_canvas.scrolled,[])


if __name__ == "__main__":
    unittest.main()
