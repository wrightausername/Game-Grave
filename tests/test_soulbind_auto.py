"""Soulbind for new games: only when switched on, only new games, never while a game runs."""
import unittest
from types import SimpleNamespace

from gg_desktop import soulbind_auto as auto
from gg_desktop import soulbind_core as sb


def game(key, name):
    return SimpleNamespace(key=key, name=name)


class NewGames(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.files = {}           # adapter id -> path, for games whose settings file "exists"

        def config(adapter, roots=None):
            return self.files.get(adapter.id)

        def apply(adapter, path, profile):
            self.calls.append(adapter.id)
            return SimpleNamespace(changes=("a", "b"))
        self.kw = dict(config=config, apply=apply)
        self.supported = next(a for a in sb.ADAPTERS)
        self.title = self.supported.names[0].title()

    def test_off_does_nothing_and_forgets_old_lists(self):
        self.assertEqual(auto.run([game("a", self.title)], {"x": 1}, {}, **self.kw), (None, [], []))
        cleared, applied, _ = auto.run([], {"x": 1}, {auto.KNOWN: ["a"], auto.WAITING: [], "other": 1}, **self.kw)
        self.assertEqual(cleared, {"other": 1})
        self.assertEqual(self.calls, [])

    def test_first_scan_only_remembers_what_is_installed(self):
        updated, applied, _ = auto.run([game("a", self.title)], {"x": 1}, {auto.SWITCH: True}, **self.kw)
        self.assertEqual(updated[auto.KNOWN], ["a"])
        self.assertEqual((applied, self.calls), ([], []))

    def test_a_new_supported_game_with_a_settings_file_is_applied_once(self):
        self.files[self.supported.id] = "C:/prefs.ini"
        settings = {auto.SWITCH: True, auto.KNOWN: ["old"], auto.WAITING: []}
        games = [game("old", "Something Else"), game("new", self.title)]
        updated, applied, _ = auto.run(games, {"x": 1}, settings, **self.kw)
        self.assertEqual(applied, [(self.supported.title, 2)])
        self.assertEqual(self.calls, [self.supported.id])
        again, applied, _ = auto.run(games, {"x": 1}, updated, **self.kw)
        self.assertEqual((again, applied, self.calls), (None, [], [self.supported.id]))

    def test_a_game_without_a_settings_file_waits_then_applies(self):
        settings = {auto.SWITCH: True, auto.KNOWN: [], auto.WAITING: []}
        games = [game("new", self.title), game("plain", "Unsupported Game")]
        updated, applied, _ = auto.run(games, {"x": 1}, settings, **self.kw)
        self.assertEqual((applied, updated[auto.WAITING]), ([], ["new"]))
        self.files[self.supported.id] = "C:/prefs.ini"
        later, applied, _ = auto.run(games, {"x": 1}, updated, **self.kw)
        self.assertEqual(applied, [(self.supported.title, 2)])
        self.assertEqual(later[auto.WAITING], [])

    def test_never_while_a_game_runs_or_without_a_profile(self):
        self.files[self.supported.id] = "C:/prefs.ini"
        settings = {auto.SWITCH: True, auto.KNOWN: [], auto.WAITING: []}
        self.assertEqual(auto.run([game("n", self.title)], {"x": 1}, settings, game_running=True, **self.kw), (None, [], []))
        self.assertEqual(auto.run([game("n", self.title)], {}, settings, **self.kw), (None, [], []))
        self.assertEqual(self.calls, [])

    def test_a_failed_apply_is_a_note_not_a_crash(self):
        self.files[self.supported.id] = "C:/prefs.ini"

        def broken(adapter, path, profile):
            raise ValueError("changed")
        _, applied, notes = auto.run([game("n", self.title)], {"x": 1}, {auto.SWITCH: True, auto.KNOWN: []},
                                     config=self.kw["config"], apply=broken)
        self.assertEqual(applied, [])
        self.assertIn("could not apply", notes[0])


if __name__ == "__main__":
    unittest.main()
