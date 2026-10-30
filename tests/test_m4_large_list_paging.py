"""M4 performance/safety: thousands of scan records do not create thousands of Tk rows.

Synthetic fixtures, no real games, save files, disk scans or windows opened.
"""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from ui import GameGraveApp
from ui_paging import DEFAULT_PAGE_SIZE, page_window


class FakeVar:
    def __init__(self, value): self.value=value
    def get(self): return self.value


class FakeTree:
    def __init__(self): self.rows={}
    def winfo_exists(self): return True
    def get_children(self): return tuple(self.rows)
    def delete(self, *items):
        for item in items: self.rows.pop(item, None)
    def insert(self, _parent, _where, *, iid, values, tags=()):
        if iid in self.rows: raise ValueError("Duplicate row key")
        self.rows[iid] = (values, tags)


class FakePage:
    def __init__(self, key, index):
        self._pager_indices={key:index}
        self.last_page=None
    def _update_inventory_page(self, key, page):
        self._pager_indices[key]=page.page
        self.last_page=page


class InventoryPaginationTests(unittest.TestCase):
    def test_large_lists_are_not_lost_or_truncated(self):
        records=list(range(50001))
        first=page_window(records,0)
        self.assertEqual(len(first.items),DEFAULT_PAGE_SIZE)
        self.assertEqual(first.items[0],0)
        self.assertIn("1–160 of 50001",first.label)
        last=page_window(records,999999)
        self.assertEqual(last.items[-1],50000)
        self.assertEqual(last.total,len(records))
        self.assertEqual(last.pages,313)
        self.assertEqual(len(last.items),81)
        self.assertEqual(records[-1],50000)

    def test_empty_and_invalid_page_requests(self):
        empty=page_window([],999)
        self.assertEqual(empty.label,"0 of 0 findings")
        self.assertEqual(empty.items,())
        self.assertEqual(empty.page,0)
        self.assertEqual(page_window([1,2,3],-100,size=2).items,(1,2))
        for size in (0, -1, 2001, 1.5, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                page_window([1,2],0,size=size)
        with self.assertRaises(ValueError):
            page_window([1,2],True)

    def test_mod_list_renders_at_most_one_page_and_lookup_matches(self):
        total=23000
        view=FakePage("mods",100)
        view.mod_tree=FakeTree()
        view.mod_filter=FakeVar("All sources")
        view.mod_search=FakeVar("")
        view.mod_sort_var=FakeVar("Largest first")
        view.mod_folders=[
            SimpleNamespace(name=f"Fake mod {i}",path=f"/no-real-files/{i}",
                status="unknown",source="Mod Organizer 2",item_count=i,
                apparent_bytes=i+1,truncated=False)
            for i in range(total)
        ]
        with patch("ui.sort_mods",side_effect=lambda items,_sort:items):
            GameGraveApp._populate_mods(view)
        self.assertEqual(len(view.mod_tree.rows),DEFAULT_PAGE_SIZE)
        self.assertEqual(len(view.mod_lookup),DEFAULT_PAGE_SIZE)
        self.assertEqual(view.mod_lookup[str(16000)].name,"Fake mod 16000")
        self.assertEqual(view.last_page.total,total)
        self.assertFalse(any("Fake mod 0"==item.name for item in view.mod_lookup.values()))

    def test_old_files_enforce_protection_on_current_page_only(self):
        view=FakePage("files",25)
        view.file_tree=FakeTree()
        view.settings={"never_touch":[]}
        view.files_sort_var=FakeVar("Largest first")
        view.old_files=[SimpleNamespace(path=f"/fake/old{i}.zip",modified=0,size=i)
                        for i in range(40000)]
        with patch("ui.sort_files",side_effect=lambda items,_sort:items), \
             patch("ui.age_text",return_value="Old"), \
             patch("ui.is_protected_path",return_value=True) as guard:
            GameGraveApp._populate_files(view)
        self.assertEqual(guard.call_count,DEFAULT_PAGE_SIZE)
        self.assertEqual(len(view.file_lookup),DEFAULT_PAGE_SIZE)
        self.assertEqual(len(view.file_tree.rows),DEFAULT_PAGE_SIZE)
        self.assertTrue(all("protected" in tag
                            for _,tag in view.file_tree.rows.values()))
        self.assertIn("old4000.zip",view.file_tree.rows["4000"][0][0])
        self.assertEqual(view.last_page.total,40000)

    def test_steam_games_and_other_launcher_records_have_bounded_rows(self):
        games=[SimpleNamespace(name=f"Game {i}",app_id=str(i),
                               last_played=None,size=100,source="Steam")
               for i in range(4000)]
        game=FakePage("games",5)
        game.game_tree=FakeTree()
        game.game_search=FakeVar("")
        game.game_sort_var=FakeVar("Name A-Z")
        game.only_old=FakeVar(False)
        game.settings={"game_stale_days":30}
        game.games=games
        with patch("ui.sort_games",side_effect=lambda items,_sort:items):
            GameGraveApp._populate_games(game)
        self.assertEqual(len(game.game_tree.rows),DEFAULT_PAGE_SIZE)
        self.assertEqual(game.game_lookup["800"].name,"Game 800")
        self.assertEqual(game.last_page.total,4000)
        other=FakePage("other",8)
        other.other_tree=FakeTree()
        other._ordered_other_games=lambda:[
            SimpleNamespace(name=f"Other {i}",launcher="Epic Games",
                            reported_bytes=100,status="recorded")
            for i in range(5000)]
        GameGraveApp._populate_other_launchers(other)
        self.assertEqual(len(other.other_tree.rows),DEFAULT_PAGE_SIZE)
        self.assertEqual(other.other_lookup["1280"].name,"Other 1280")


if __name__=="__main__":
    unittest.main()
