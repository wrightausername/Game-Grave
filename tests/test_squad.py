import base64
import tempfile
import unittest
import zlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from gg_desktop import squad_core as sq

ACF = '''"AppWorkshop"
{
\t"appid"\t\t"489830"
\t"WorkshopItemsInstalled"
\t{
\t\t"1111111"
\t\t{
\t\t\t"size"\t\t"1000"
\t\t\t"timeupdated"\t\t"1700000000"
\t\t}
\t\t"2222222"
\t\t{
\t\t\t"size"\t\t"2000"
\t\t\t"timeupdated"\t\t"1700000500"
\t\t}
\t\t"abc"
\t\t{
\t\t\t"timeupdated"\t\t"1"
\t\t}
\t}
}
'''


class SquadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        lib = self.root / "lib"
        (lib / "steamapps" / "workshop").mkdir(parents=True)
        (lib / "steamapps" / "workshop" / "appworkshop_489830.acf").write_text(ACF, encoding="utf-8")
        self.library = str(lib)
        local = self.root / "Local"
        inst = local / "ModOrganizer" / "Skyrim SE"
        (inst / "profiles" / "Co-op").mkdir(parents=True)
        (inst / "ModOrganizer.ini").write_text("[General]\ngameName=Skyrim Special Edition\nselected_profile=@ByteArray(Co-op)\n", encoding="utf-8")
        (inst / "profiles" / "Co-op" / "modlist.txt").write_text("# comment\n+SkyUI\n-Disabled Mod\n+USSEP\n", encoding="utf-8")
        (local / "Skyrim Special Edition").mkdir()
        (local / "Skyrim Special Edition" / "plugins.txt").write_text("# list\n*SkyUI_SE.esp\nNotEnabled.esp\n*Unofficial Skyrim Special Edition Patch.esp\n", encoding="utf-8")
        (self.root / "Roaming" / "Vortex").mkdir(parents=True)
        self.roots = {"local": [local], "roaming": [self.root / "Roaming"]}

    def mine(self):
        return sq.read_setup("Skyrim Special Edition", "489830", self.library, self.roots, datetime(2026, 11, 9, 12, 0))

    def test_reads_the_three_real_sources_and_says_what_it_found(self):
        setup = self.mine()
        kinds = sorted({i.kind for i in setup.items})
        self.assertEqual(kinds, ["mo2", "plugin", "workshop"])
        self.assertEqual([i.key for i in setup.items if i.kind == "workshop"], ["1111111", "2222222"])
        self.assertEqual([i.label for i in setup.items if i.kind == "mo2"], ["SkyUI", "USSEP"])
        self.assertEqual(len([i for i in setup.items if i.kind == "plugin"]), 2)
        self.assertTrue(setup.read_any)
        text = " | ".join(setup.notes)
        self.assertIn("Steam Workshop: 2 items", text)
        self.assertIn("Mod Organizer 2: 2 items", text)
        self.assertIn("Vortex: its mod lists cannot be read yet", text)

    def test_nothing_readable_is_stated_not_guessed(self):
        setup = sq.read_setup("Cyberpunk 2077", "1091500", self.library, self.roots)
        self.assertFalse(setup.read_any)
        self.assertEqual(setup.items, [])
        self.assertIn("nothing found", setup.notes[0])

    def test_code_round_trips_and_holds_no_paths(self):
        setup = self.mine()
        code = sq.make_code(setup)
        back = sq.read_code(code)
        self.assertEqual(back.game, setup.game)
        self.assertEqual(back.items, setup.items)
        raw = zlib.decompress(base64.urlsafe_b64decode(code[len(sq.CODE_PREFIX):] + "==")).decode()
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("Users", raw)

    def test_junk_and_hostile_codes_are_refused(self):
        for bad in ("hello", "", sq.CODE_PREFIX + "!!!", sq.CODE_PREFIX + "A" * 30, "x" * 30000):
            with self.assertRaises(ValueError):
                sq.read_code(bad)
        bomb = sq.CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(b"[" + b"0," * 2_000_000 + b"0]", 9)).decode()
        with self.assertRaises(ValueError):
            sq.read_code(bomb)

        def forge(payload):
            import json
            return sq.CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode())).decode()
        for payload in ({"v": 2, "g": "G", "i": []}, {"v": 1, "g": "G", "i": [["evil", "k", "l", ""]]},
                        {"v": 1, "g": "G", "i": [["workshop", "12;calc", "l", ""]]},
                        {"v": 1, "g": "G", "i": [["mo2", "k", "l", "notdigits"]]},
                        {"v": 1, "g": "G", "i": [["mo2", "k"]]}):
            with self.assertRaises(ValueError):
                sq.read_code(forge(payload))

    def test_compare_finds_missing_different_and_extra(self):
        mine = self.mine()
        theirs = sq.Setup("Skyrim Special Edition", [
            sq.Item("workshop", "1111111", "w", "1700000000"),      # same
            sq.Item("workshop", "2222222", "w", "1700009999"),      # different time
            sq.Item("workshop", "3333333", "w", "1"),               # missing
            sq.Item("mo2", "skyui", "SkyUI"),                       # same
            sq.Item("mo2", "newmod", "New Mod")], read_any=True)    # missing
        result = sq.compare(theirs, mine)
        self.assertEqual(len(result.same), 2)
        self.assertEqual([i.key for i in result.missing], ["3333333", "newmod"])
        self.assertEqual([t.key for t, _ in result.different], ["2222222"])
        self.assertTrue(any(i.key == "ussep" for i in result.extra))
        self.assertIn("2 missing", result.summary)
        self.assertIn("cannot tell", result.summary)
        self.assertEqual(sq.workshop_url(result.missing[0]), "steam://url/CommunityFilePage/3333333")
        self.assertIsNone(sq.workshop_url(result.missing[1]))

    def test_matching_setups_say_so(self):
        mine = self.mine()
        result = sq.compare(sq.read_code(sq.make_code(mine)), mine)
        self.assertEqual((result.missing, result.different, result.extra), ([], [], []))
        self.assertTrue(result.summary.startswith("Nothing is missing"))

    def test_wrong_game_unreadable_and_empty_cases(self):
        with self.assertRaises(ValueError):
            sq.compare(sq.Setup("Fallout 4", [sq.Item("mo2", "a", "A")], read_any=True), self.mine())
        blind = sq.Setup("Skyrim Special Edition", [], read_any=False)
        result = sq.compare(sq.Setup("Skyrim Special Edition", [sq.Item("mo2", "a", "A")], read_any=True), blind)
        self.assertFalse(result.comparable)
        self.assertIn("will not guess", result.summary)
        empty = sq.compare(sq.Setup("Skyrim Special Edition", [], read_any=True), self.mine())
        self.assertFalse(empty.comparable)

    def test_snapshots_round_trip_and_stay_per_game(self):
        root = self.root / "squad"
        path = sq.save_snapshot(self.mine(), root, datetime(2026, 11, 9, 12, 0, 0))
        sq.save_snapshot(sq.Setup("Fallout 4", [sq.Item("mo2", "a", "A")], read_any=True), root, datetime(2026, 11, 9, 12, 0, 1))
        listed = sq.list_snapshots("Skyrim Special Edition", root)
        self.assertEqual([p for p, _m, _n in listed], [path])
        self.assertEqual(listed[0][2], len(self.mine().items))
        self.assertEqual(sq.load_snapshot(path).items, self.mine().items)
        path.write_text("junk", encoding="utf-8")
        with self.assertRaises(ValueError):
            sq.load_snapshot(path)
        self.assertEqual(sq.list_snapshots("Skyrim Special Edition", root), [])


if __name__ == "__main__":
    unittest.main()
