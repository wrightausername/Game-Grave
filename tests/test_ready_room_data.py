"""Ready Room must never turn a visual reference into evidence about a PC."""
from dataclasses import asdict
from types import SimpleNamespace
import unittest

from gg_desktop.backend import Inventory
from gg_desktop.ready_room_data import live_ready_room, reference_ready_room


class ReadyRoomEvidenceTests(unittest.TestCase):
    def test_no_scan_has_unknown_counts_and_no_health_or_backup_claim(self):
        state = live_ready_room(Inventory())
        self.assertFalse(state.reference)
        self.assertEqual(state.counts, ("—",) * 5)
        self.assertFalse(state.patches)
        self.assertFalse(state.games)
        self.assertIsNone(state.health_score)
        self.assertEqual(state.backup_title, "Backup history unavailable")
        self.assertTrue(all(tone == "muted" for _, tone in state.health))

    def test_install_and_last_play_date_do_not_prove_playtime_or_up_to_date(self):
        inventory = Inventory(games=[SimpleNamespace(
            name="Cyberpunk 2077", key="local:1", last_played_at=1700000000,
            status="Installed (Steam record)")], scanned_at="2026-11-06")
        state = live_ready_room(inventory)
        self.assertEqual(state.games[0].name, "Cyberpunk 2077")
        self.assertEqual(state.games[0].key, "local:1")
        self.assertEqual(state.games[0].hours, "— hrs")
        self.assertEqual(state.games[0].status, "Recorded install")
        self.assertEqual(state.games[0].tone, "muted")
        self.assertEqual(state.games[0].artwork, "cyberpunk")
        self.assertEqual(state.counts, ("—",) * 5)

    def test_mod_locations_and_save_discovery_are_not_installed_mod_or_backup_counts(self):
        inventory = Inventory(mods=[object(), object()], saves=[object()] * 6,
                              scanned_at="2026-11-06")
        state = live_ready_room(inventory)
        self.assertEqual(state.mod_stats[0], ("2", "Mod locations"))
        self.assertEqual(state.mod_stats[1][0], "—")
        self.assertNotEqual(state.mod_state, "All Clear")
        self.assertEqual(state.backup_title, "Backup history unavailable")

    def test_disk_reading_does_not_verify_files_conflicts_or_manager_online_status(self):
        state = live_ready_room(Inventory(), disk_free_percent=25)
        self.assertEqual(state.health[0], ("Storage available", "green"))
        self.assertTrue(all(tone == "muted" for _, tone in state.health[1:]))
        self.assertIsNone(state.health_score)
        low = live_ready_room(Inventory(), disk_free_percent=2)
        self.assertEqual(low.health[0], ("Storage running low", "amber"))

    def test_partial_scan_is_visible_and_session_backups_are_labeled(self):
        state = live_ready_room(Inventory(warnings=["Old Files folder unavailable"]), session_backups=2)
        self.assertEqual(state.health[2], ("Partial scan: review warnings", "amber"))
        self.assertEqual(state.backup_title, "2 Verified Backups")
        self.assertEqual(state.backup_note, "Created this session")

    def test_reference_data_is_explicit_and_never_changes_inventory(self):
        inventory = Inventory()
        before = asdict(inventory)
        fixture = reference_ready_room()
        self.assertTrue(fixture.reference)
        self.assertEqual(len(fixture.patches), 5)
        self.assertEqual(len(fixture.games), 5)
        self.assertEqual(fixture.health_score, 92)
        self.assertEqual(asdict(inventory), before)
        self.assertFalse(live_ready_room(inventory).reference)
        self.assertIsNone(live_ready_room(inventory).health_score)


if __name__ == "__main__":
    unittest.main()
