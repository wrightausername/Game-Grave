"""Explicit Graveyard override safety tests. Never recycle real user data."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import tempfile
import time
import unittest

from core import OldFile
from graveyard import GraveyardEntry
from graveyard_override import (
    ACKNOWLEDGEMENT, OverrideRefused, _critical_path,
    _metadata_fingerprint, override_eligibility, recycle_selected_override,
)


def snapshot_file(path: Path) -> OldFile:
    st = path.stat()
    return OldFile(str(path), st.st_size, st.st_mtime, st.st_dev,
                   st.st_ino, st.st_mtime_ns, st.st_nlink)


def snapshot_entry(path: Path, *, kind: str) -> GraveyardEntry:
    return GraveyardEntry(
        key=(f"steam:99" if kind == "game" else
             "mod:" + str(path).casefold() if kind == "mod" else
             "file:" + str(path).casefold()),
        name=path.name, path=str(path),
        category=("Neglected installed game" if kind == "game" else
                  "Managed mod folder" if kind == "mod" else
                  "Old file from reviewed folder"),
        apparent_bytes=path.stat().st_size, age_days=900,
        relationship="Installed or managed: do not remove by default",
        finding="Owner explicitly selected the item.",
        protection="Protected by Game Grave", can_recycle=False,
        old_file=snapshot_file(path) if path.is_file() else None,
    )


def inventory_for(entry, kind):
    return SimpleNamespace(
        graveyard=[entry],
        steam=[SimpleNamespace(install_path=entry.path)] if kind == "game" else [],
        mods=[SimpleNamespace(path=entry.path)] if kind == "mod" else [],
        files=[entry.old_file] if kind == "file" else [],
        screenshots=[], recordings=[],
    )


class ProtectedItemOverrideTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)

    def test_owner_can_choose_to_override_managed_mod_folder(self):
        path = self.root / "Managed Mods"
        path.mkdir()
        (path / "loadout.txt").write_text("keep safe by default")
        entry = snapshot_entry(path, kind="mod")
        allowed, reason = override_eligibility(entry, inventory_for(entry, "mod"))
        self.assertTrue(allowed, reason)
        self.assertIn("One-time", reason)

    def test_owner_can_choose_to_override_detected_installed_game(self):
        path = self.root / "Game Install"
        path.mkdir()
        (path / "game.exe").write_bytes(b"synthetic executable")
        entry = snapshot_entry(path, kind="game")
        allowed, reason = override_eligibility(entry, inventory_for(entry, "game"))
        self.assertTrue(allowed, reason)

    def test_owner_can_override_protected_scanned_file(self):
        path = self.root / "Mods"
        path.mkdir()
        modfile = path / "mod.zip"
        modfile.write_bytes(b"dummy")
        entry = snapshot_entry(modfile, kind="file")
        self.assertTrue(override_eligibility(entry, inventory_for(entry, "file"))[0])

    def test_item_not_in_scan_cannot_be_overridden(self):
        path = self.root / "private"
        path.mkdir()
        entry = snapshot_entry(path, kind="mod")
        inv = inventory_for(entry, "mod")
        inv.graveyard = []
        self.assertFalse(override_eligibility(entry, inv)[0])

    def test_tampered_entry_same_key_different_category_rejected(self):
        path = self.root / "Mods"
        path.mkdir()
        entry = snapshot_entry(path, kind="mod")
        inv = inventory_for(entry, "mod")
        changed = replace(entry, finding="invented evidence")
        self.assertFalse(override_eligibility(changed, inv)[0])

    def test_arbitrary_parent_directory_not_trusted(self):
        path = self.root / "Mods"
        path.mkdir()
        entry = snapshot_entry(path, kind="mod")
        inv = inventory_for(entry, "mod")
        inv.mods = [SimpleNamespace(path=str(path / "child"))]
        self.assertFalse(override_eligibility(entry, inv)[0])

    def test_home_and_drive_root_are_not_overridable(self):
        self.assertTrue(_critical_path(Path.home()))
        self.assertTrue(_critical_path(Path(Path.cwd().anchor)))

    def test_symlinked_folder_rejected(self):
        source = self.root / "source"
        source.mkdir()
        target = self.root / "linked"
        try:
            target.symlink_to(source, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not allow symlinks")
        entry = snapshot_entry(target, kind="mod")
        self.assertFalse(override_eligibility(
            entry, inventory_for(entry, "mod"))[0])

    def test_nested_symlink_refused_during_full_tree_scan(self):
        folder = self.root / "mods"
        folder.mkdir()
        (folder / "normal.txt").write_bytes(b"x")
        other = self.root / "private"
        other.mkdir()
        try:
            (folder / "shortcut").symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not allow symlinks")
        with self.assertRaisesRegex(OverrideRefused, "link|junction"):
            _metadata_fingerprint(folder)
        self.assertTrue(other.exists())

    def test_tree_fingerprint_changes_when_member_changes(self):
        folder = self.root / "Game"
        folder.mkdir()
        child = folder / "data.bin"
        child.write_bytes(b"hi")
        first, size, count = _metadata_fingerprint(folder)
        self.assertEqual(size, 2)
        self.assertEqual(count, 2)
        child.write_bytes(b"changed payload")
        second, _, _ = _metadata_fingerprint(folder)
        self.assertNotEqual(first, second)

    def test_acknowledgement_required_even_when_scan_is_valid(self):
        folder = self.root / "mods"
        folder.mkdir()
        entry = snapshot_entry(folder, kind="mod")
        with self.assertRaisesRegex(OverrideRefused, "confirmation"):
            recycle_selected_override(
                entry, inventory_for(entry, "mod"), (), "test-session")
        self.assertTrue(folder.exists())

    def test_screenshots_require_existing_separate_preview_flow(self):
        path = self.root / "capture.png"
        path.write_bytes(b"image")
        entry = replace(snapshot_entry(path, kind="file"),
                        category="Old game screenshot")
        self.assertFalse(override_eligibility(
            entry, inventory_for(entry, "file"))[0])

    @unittest.skipUnless(os.name == "nt", "Windows Shell override canary test")
    def test_authorized_windows_path_invokes_recycle_canary_first(self):
        folder = self.root / "Game Install"
        folder.mkdir()
        (folder / "game.exe").write_bytes(b"example")
        entry = snapshot_entry(folder, kind="game")
        inv = inventory_for(entry, "game")
        with patch("graveyard_override._recycle_canary_on_local_volume", return_value=True) as canary, \
             patch("graveyard_override.core._recycle_shell_session_ready", return_value=True), \
             patch("graveyard_override.core._shell_recycle_operation") as shell, \
             patch("graveyard_override.register_recycle"), \
             patch("graveyard_override._run_ps", return_value="AVAILABLE"):
            report = recycle_selected_override(
                entry, inv, (), "unit-test", acknowledged=True)
            canary.assert_called_once()
            shell.assert_called_once_with(folder)
            self.assertTrue(report["recovery_verified"])
            self.assertTrue(folder.exists(), "Mocked Shell must leave test fixtures untouched.")


if __name__ == "__main__":
    unittest.main()
