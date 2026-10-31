"""User-reported Graveyard actions and game capture discovery regressions.

Tests create only disposable local fixtures and never delete real user content.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import OldFile
from graveyard import build_graveyard
from recordings import find_old_recordings
from ui import GameGraveApp


class RecordingDiscoveryTests(unittest.TestCase):
    def _old_file(self, path, days=550):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic game clip")
        stamp = time.time() - days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_default_capture_folder_does_not_include_personal_movies(self):
        with tempfile.TemporaryDirectory() as base:
            home = Path(base)
            target = self._old_file(home / "Videos" / "Captures" / "gameplay.mp4")
            holiday = self._old_file(home / "Videos" / "vacation.mp4")
            recent = self._old_file(home / "Videos" / "Captures" / "yesterday.mp4", days=3)
            result = find_old_recordings(180, home=home)
            paths = {Path(item.path) for item in result}
            self.assertIn(target, paths)
            self.assertNotIn(holiday, paths)
            self.assertNotIn(recent, paths)
            self.assertTrue(all(p.exists() for p in (target, holiday, recent)))

    def test_explicit_capture_root_and_extension_filter(self):
        with tempfile.TemporaryDirectory() as base:
            folder = Path(base) / "custom-captures"
            movie = self._old_file(folder / "random-title.mkv")
            other = self._old_file(folder / "gameplay.txt")
            files = find_old_recordings(180, [str(folder)], home=Path(base) / "not-user")
            self.assertEqual([Path(file.path) for file in files], [movie])
            self.assertTrue(other.is_file())

    def test_recordings_appear_reviewable_but_never_auto_deleted(self):
        with tempfile.TemporaryDirectory() as base:
            p = self._old_file(Path(base) / "Captures" / "match.mp4")
            f = OldFile(str(p), p.stat().st_size, p.stat().st_mtime)
            now = time.time()
            results = build_graveyard([], [], [], 365, now=now, recordings=[f])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].category, "Old game recording")
            self.assertTrue(results[0].can_recycle)
            guarded = build_graveyard([], [], [], 365, never_touch=[str(p)],
                                       now=now, recordings=[f])
            self.assertFalse(guarded[0].can_recycle)
            self.assertTrue(p.exists())


class GraveyardActionTests(unittest.TestCase):
    def test_protected_file_cannot_be_deleted_even_if_checked(self):
        with tempfile.TemporaryDirectory() as base:
            p = Path(base) / "skyrim-mod.zip"
            p.write_bytes(b"test archive")
            record = OldFile(str(p), p.stat().st_size, time.time() - 900 * 86400)
            entry = build_graveyard([], [], [record], 365, [str(p)])[0]
            fake = SimpleNamespace(graveyard_lookup={entry.key: entry})
            with patch("ui.messagebox.showwarning") as warning,                  patch("ui.messagebox.askyesno") as approval,                  patch("ui.recycle_file") as delete:
                GameGraveApp._grave_recycle_ids(fake, [entry.key])
            warning.assert_called_once()
            approval.assert_not_called()
            delete.assert_not_called()
            self.assertTrue(p.exists())

    def test_protection_action_updates_graveyard_inventory_immediately(self):
        with tempfile.TemporaryDirectory() as base:
            p = Path(base) / "skyrim-mod.zip"
            p.write_bytes(b"test archive")
            record = OldFile(str(p), p.stat().st_size, time.time() - 900 * 86400)
            entry = build_graveyard([], [], [record], 365)[0]
            fake = SimpleNamespace(
                settings={"graveyard_days": 365, "never_touch": [], "graveyard_watchlist": []},
                games=[], mod_folders=[], old_files=[record], recordings=[],
                grave_checked={entry.key}, _grave_selected_entry=lambda: entry,
                _populate_graveyard=Mock(), status_text=SimpleNamespace(set=Mock()))
            with patch("ui.save_settings"), patch("ui.messagebox.showinfo"):
                GameGraveApp._grave_toggle_protection(fake)
            self.assertEqual(fake.settings["never_touch"], [os.path.abspath(str(p))])
            self.assertFalse(fake.graveyard_entries[0].can_recycle)
            self.assertFalse(fake.grave_checked)
            fake._populate_graveyard.assert_called_once()

    def test_windows_recycle_failure_is_reported_not_claimed_as_deleted(self):
        from cleanup_actions import recycle_reviewed_entries
        with tempfile.TemporaryDirectory() as base:
            p = Path(base) / "skyrim-mod.zip"
            p.write_bytes(b"test archive")
            stamp = time.time() - 900 * 86400
            os.utime(p, (stamp, stamp))
            entry = build_graveyard([], [], [
                OldFile(str(p), p.stat().st_size, p.stat().st_mtime)])[0]
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file",
                       side_effect=RuntimeError("Windows recycle unavailable")), \
                 patch("cleanup_actions.register_recycle") as registration:
                result = recycle_reviewed_entries([entry], [], "disposable-qa")
            self.assertEqual(result["completed"], 0)
            self.assertEqual(len(result["skipped"]), 1)
            registration.assert_not_called()
            self.assertTrue(p.exists())

    def test_english_game_dna_summary_has_no_action_side_effects(self):
        class Var:
            def __init__(self, value): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value
        fake = SimpleNamespace(
            _dna_game_options={"My Game": {"game":"My Game","launcher":"Steam",
                                          "assets":[1, 2]}},
            dna_pick_var=Var("My Game"), dna_explanation_var=Var(""))
        GameGraveApp._dna_selected_game(fake)
        self.assertIn("2 mod-storage location(s)", fake.dna_explanation_var.get())
        self.assertIn("not permission to delete", fake.dna_explanation_var.get())


if __name__ == "__main__":
    unittest.main()
