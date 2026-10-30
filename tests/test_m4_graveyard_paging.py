"""M4 Graveyard paging safety. Synthetic entries only, no disk or recycle operations."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui import GameGraveApp
from ui_paging import DEFAULT_PAGE_SIZE


class Var:
    def __init__(self, value=""):
        self.value=value
    def get(self): return self.value
    def set(self, value): self.value=value


class FakeTree:
    def __init__(self):
        self.rows={}
        self.selected=()
    def winfo_exists(self): return True
    def selection(self): return self.selected
    def selection_set(self, choices): self.selected=tuple(choices)
    def get_children(self): return tuple(self.rows)
    def delete(self, *rows):
        for key in rows: self.rows.pop(key,None)
        self.selected=()
    def insert(self, _parent, _where, *, iid, values, tags=()):
        if iid in self.rows: raise AssertionError("duplicate visual row")
        self.rows[iid]=list(values)
    def set(self, key, column, value):
        assert column=="check", column
        assert key in self.rows, f"offscreen row mutation: {key}"
        self.rows[key][0]=value


def finding(i):
    return SimpleNamespace(key=f"entry-{i}",name=f"Fake archive {i}",
        category="Archive",age_days=400,apparent_bytes=100+i,
        can_recycle=(i % 5 != 0),old_file=None,
        path=f"/synthetic/never-real/{i}",protection="Not classified")


class FakeGrave:
    _grave_update_count=GameGraveApp._grave_update_count
    _grave_refresh_checks=GameGraveApp._grave_refresh_checks
    _grave_recycle_all=GameGraveApp._grave_recycle_all
    _grave_select_all=GameGraveApp._grave_select_all
    _grave_select_eligible=GameGraveApp._grave_select_eligible
    _grave_clear_checks=GameGraveApp._grave_clear_checks
    _grave_toggle=GameGraveApp._grave_toggle

    def __init__(self, size=10001):
        self.grave_tree=FakeTree()
        self.grave_checked={"entry-1"}
        self.grave_count_var=Var()
        self.graveyard_entries=[finding(i) for i in range(size)]
        self.graveyard_lookup={}
        self._pager_indices={"grave":0}
        self._grave_page_keys=set()
        self.grave_search_var=Var("")
        self.grave_category_var=Var("All types")
        self.grave_status_var=Var("All findings")
        self.grave_min_size_var=Var("Any size")
        self.grave_sort_var=Var("Size")
        self.grave_order_var=Var("Descending")
        self._grave_summary=""
        self._grave_can_override=lambda entry:False
        self.last_page=None
        self.recycle_asked=[]
    def _update_inventory_page(self,key,page):
        assert key=="grave"
        self._pager_indices[key]=page.page
        self.last_page=page
    def _grave_recycle_ids(self,ids):
        self.recycle_asked.append(list(ids))


class GraveyardPagedReviewTests(unittest.TestCase):
    def populate(self, grave):
        with patch("ui.filter_sort_graveyard",
                   side_effect=lambda entries, **kwargs:entries):
            GameGraveApp._populate_graveyard(grave)

    def test_large_graveyard_creates_bounded_rows_without_dropping_ownership(self):
        view=FakeGrave(10001)
        self.populate(view)
        self.assertEqual(len(view.grave_tree.rows), DEFAULT_PAGE_SIZE)
        self.assertEqual(len(view.graveyard_lookup),10001)
        self.assertEqual(view.last_page.total,10001)
        self.assertEqual(len(view._grave_page_keys),DEFAULT_PAGE_SIZE)
        self.assertIn("entry-1",view.grave_checked)
        self.assertIn("entry-1",view.grave_tree.rows)
        self.assertIn("checked",view.grave_count_var.get())

    def test_checks_persist_across_pages_and_only_current_rows_are_mutated(self):
        view=FakeGrave(401)
        self.populate(view)
        view._grave_select_eligible()
        self.assertNotIn("entry-0",view.grave_checked)
        self.assertIn("entry-1",view.grave_checked)
        self.assertIn("entry-159",view.grave_checked)
        view._pager_indices["grave"]=1
        self.populate(view)
        self.assertEqual(len(view.grave_tree.rows),160)
        self.assertIn("entry-1",view.grave_checked)
        view._grave_select_all()
        self.assertIn("entry-160",view.grave_checked)
        self.assertEqual(len(view.grave_checked),128+160)
        self.assertNotIn("entry-320",view.grave_checked)
        view._grave_toggle("entry-321")
        self.assertNotIn("entry-321",view.grave_checked)
        view._grave_clear_checks()
        self.assertEqual(view.grave_checked,set())
        self.assertTrue(all(row[0]=="☐" for row in view.grave_tree.rows.values()))

    def test_recycle_eligible_only_targets_current_page(self):
        view=FakeGrave(5000)
        self.populate(view)
        view._pager_indices["grave"]=12
        self.populate(view)
        view._grave_recycle_all()
        requested=view.recycle_asked[0]
        self.assertLessEqual(len(requested),160)
        self.assertTrue(all(key in view._grave_page_keys for key in requested))
        self.assertTrue(all(view.graveyard_lookup[k].can_recycle for k in requested))

    def test_late_batch_is_refused_before_any_cleanup_or_confirmation(self):
        view=FakeGrave(500)
        self.populate(view)
        request=[f"entry-{i}" for i in range(161)]
        with patch("ui.messagebox.showwarning") as warning, \
             patch("ui.messagebox.askyesno") as approval, \
             patch("ui.log_event") as log, \
             patch("ui.recycle_file") as recycle:
            GameGraveApp._grave_recycle_ids(view, request)
        warning.assert_called_once()
        approval.assert_not_called()
        log.assert_not_called()
        recycle.assert_not_called()

    def test_filter_removes_invisible_checked_items(self):
        view=FakeGrave(250)
        self.populate(view)
        view.grave_checked.update({"entry-2","entry-200"})
        with patch("ui.filter_sort_graveyard", side_effect=
                   lambda entries,**kwargs:entries[:25]):
            GameGraveApp._populate_graveyard(view)
        self.assertEqual(view.grave_checked,{"entry-1","entry-2"})
        self.assertEqual(len(view.grave_tree.rows),25)
        self.assertTrue(view.last_page.page==0)


if __name__=="__main__":
    unittest.main()
