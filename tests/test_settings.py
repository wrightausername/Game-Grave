import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import core
from gg_desktop import settings_data as data
from gg_desktop import settings_rules as rules
from gg_desktop import settings_store as store
from gg_desktop import settings_system as system


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {"LOCALAPPDATA": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_other_tabs_keys_survive_a_restart_and_the_next_save(self):
        settings = store.load_settings()
        settings.update(assistant_chats=[{"id": "a"}], undo_hidden=["x"], dna_links={"g": ["p"]}, never_touch=["C:/keep"])
        core.save_settings(settings)
        self.assertNotIn("assistant_chats", core.load_settings(), "the shared loader still drops them")
        reopened = store.load_settings()
        self.assertEqual(reopened["assistant_chats"], [{"id": "a"}])
        self.assertEqual(reopened["undo_hidden"], ["x"])
        self.assertEqual(reopened["dna_links"], {"g": ["p"]})
        reopened["scan_on_launch"] = True
        core.save_settings(reopened)
        again = json.loads((core.config_dir() / "settings.json").read_text())
        self.assertIn("assistant_chats", again)
        self.assertEqual(again["never_touch"], ["C:/keep"])

    def test_known_keys_keep_the_shared_loaders_type_checks(self):
        (core.config_dir()).mkdir(parents=True)
        (core.config_dir() / "settings.json").write_text(json.dumps({"files_stale_days": "soon", "extra": 1}))
        loaded = store.load_settings()
        self.assertEqual(loaded["files_stale_days"], 180)
        self.assertEqual(loaded["extra"], 1)

    def test_damaged_oversized_or_duplicate_files_fall_back(self):
        path = core.config_dir() / "settings.json"
        path.parent.mkdir(parents=True)
        for raw in (b"not json", b'{"a":1,"a":2}', b"[1,2]", b" " * (core.MAX_SETTINGS_BYTES + 1)):
            path.write_bytes(raw)
            self.assertEqual(store.load_settings(), core.default_settings())

    def test_no_file_gives_the_defaults(self):
        self.assertEqual(store.load_settings(), core.default_settings())


class Prefs(unittest.TestCase):
    def test_current_repairs_bad_values(self):
        bad = {"start_minimized": "yes", "files_stale_days": 7, "graveyard_days": True,
               "excluded_folders": ["relative", 4, "/a", "/a"], "steam_artwork_downloads": "no"}
        got = data.current(bad)
        self.assertIs(got["start_minimized"], False)
        self.assertEqual((got["files_stale_days"], got["graveyard_days"]), (180, 365))
        self.assertEqual(got["excluded_folders"], ["/a"] if Path("/a").is_absolute() else [])
        self.assertIs(got["steam_artwork_downloads"], True)

    def test_assistant_tab_is_optional_and_off_by_default(self):
        self.assertIs(data.OWNED["assistant_enabled"], False)
        self.assertIs(data.current({})["assistant_enabled"], False)
        self.assertIs(data.current({"assistant_enabled": "yes"})["assistant_enabled"], False)
        self.assertIs(data.current({"assistant_enabled": True})["assistant_enabled"], True)
        self.assertIs(data.defaults()["assistant_enabled"], False)

    def test_apply_changes_only_owned_keys(self):
        saved = {"never_touch": ["/p"], "assistant_chats": [1], "start_minimized": False}
        out = data.apply(saved, dict(data.current(saved), start_minimized=True))
        self.assertIs(out["start_minimized"], True)
        self.assertEqual(out["never_touch"], ["/p"])
        self.assertEqual(out["assistant_chats"], [1])

    def test_changed_and_defaults(self):
        base = data.defaults()
        edited = dict(base, scan_on_launch=True, excluded_folders=["/x"])
        self.assertEqual(data.changed(base, edited), ["scan_on_launch", "excluded_folders"])
        self.assertEqual(data.changed(base, data.defaults()), [])
        data.defaults()["excluded_folders"].append("/leak")
        self.assertEqual(data.OWNED["excluded_folders"], [])

    def test_exclusion_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(data.exclusion_problem(tmp, []), "")
            self.assertIn("already", data.exclusion_problem(tmp, [tmp]))
            self.assertIn("existing", data.exclusion_problem(os.path.join(tmp, "missing"), []))
            self.assertIn("At most", data.exclusion_problem(tmp, [f"/f{i}" for i in range(data.MAX_FOLDERS)]))
        self.assertIn("drive", data.exclusion_problem(Path(tmp).anchor, []))


class Exchange(unittest.TestCase):
    def test_export_holds_only_preferences_and_folders(self):
        settings = dict(core.default_settings(), assistant_chats=[{"secret": 1}], undo_hidden=["a"], never_touch=["/p"])
        payload = json.loads(data.export_text(settings))
        self.assertEqual(payload["app"], "Game Grave")
        self.assertNotIn("assistant_chats", payload["settings"])
        self.assertNotIn("undo_hidden", payload["settings"])
        self.assertEqual(payload["settings"]["never_touch"], ["/p"])

    def test_import_rejects_other_files(self):
        for raw in (b"x", b"[]", b'{"app":"Other","format":1,"settings":{}}', b'{"app":"Game Grave","format":2,"settings":{}}',
                    b"0" * (core.MAX_SETTINGS_BYTES + 1)):
            with self.assertRaises(ValueError):
                data.import_settings(raw, {})

    def test_import_never_removes_a_protection_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = os.path.join(tmp, "keep")
            new = os.path.join(tmp, "new")
            os.makedirs(keep)
            os.makedirs(new)
            incoming = {"app": "Game Grave", "format": 1,
                        "settings": {"never_touch": [new], "scan_on_launch": True, "files_stale_days": 90,
                                     "excluded_folders": [new, os.path.join(tmp, "gone")]}}
            report = data.import_settings(json.dumps(incoming).encode(), {"never_touch": [keep], "assistant_chats": [1]})
            self.assertEqual(report.settings["never_touch"], [keep, new])
            self.assertEqual(report.settings["excluded_folders"], [new])
            self.assertIs(report.settings["scan_on_launch"], True)
            self.assertEqual(report.settings["assistant_chats"], [1])
            self.assertTrue(any("skipped" in n for n in report.notes))
            empty = {"app": "Game Grave", "format": 1, "settings": {"never_touch": []}}
            self.assertEqual(data.import_settings(json.dumps(empty).encode(), {"never_touch": [keep]}).settings["never_touch"], [keep])

    def test_import_ignores_unknown_and_unsafe_keys(self):
        incoming = {"app": "Game Grave", "format": 1, "settings": {"assistant_chats": [9], "auto_enabled": True, "scan_folder": "relative"}}
        out = data.import_settings(json.dumps(incoming).encode(), {"auto_enabled": False}).settings
        self.assertIs(out["auto_enabled"], False)
        self.assertNotIn("assistant_chats", out)
        self.assertNotIn("scan_folder", out)


class Exclusions(unittest.TestCase):
    def test_inside_matches_folders_not_name_prefixes(self):
        self.assertTrue(rules.inside("/games/mods/a.zip", ["/games/mods"]))
        self.assertTrue(rules.inside("/games/mods", ["/games/mods"]))
        self.assertFalse(rules.inside("/games/mods2/a.zip", ["/games/mods"]))
        self.assertFalse(rules.inside("/games", ["/games/mods"]))

    def test_filter_inventory_drops_only_inside_items_and_keeps_saves(self):
        inv = SimpleNamespace(
            steam=[SimpleNamespace(install_path="/lib/a"), SimpleNamespace(install_path="/skip/b")],
            other=[], games=[SimpleNamespace(install_path="/skip/b"), SimpleNamespace(install_path="/lib/a")],
            mods=[SimpleNamespace(path="/skip/m"), SimpleNamespace(path="/lib/m")],
            files=[SimpleNamespace(path="/skip/f")], recordings=[], screenshots=[SimpleNamespace(nopath=1)],
            saves=[SimpleNamespace(path="/skip/save")])
        left_out = rules.filter_inventory(inv, ["/skip"])
        self.assertEqual(left_out, 4)
        self.assertEqual([g.install_path for g in inv.games], ["/lib/a"])
        self.assertEqual([m.path for m in inv.mods], ["/lib/m"])
        self.assertEqual(len(inv.screenshots), 1, "an item with no path is never dropped")
        self.assertEqual(len(inv.saves), 1, "saves are never filtered")

    def test_no_folders_changes_nothing(self):
        inv = SimpleNamespace(games=[SimpleNamespace(install_path="/a")])
        self.assertEqual(rules.filter_inventory(inv, []), 0)
        self.assertEqual(len(inv.games), 1)


class FakeRegistry:
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = 1, 2, 3, 4

    def __init__(self):
        self.values = {}

    class _Key:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def OpenKey(self, *_):
        return self._Key(self.values)

    CreateKeyEx = OpenKey

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], 1

    def SetValueEx(self, key, name, _r, _k, value):
        key.values[name] = value

    def DeleteValue(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]


class Autostart(unittest.TestCase):
    def test_round_trip_uses_the_current_executable_only(self):
        reg = FakeRegistry()
        self.assertFalse(system.is_enabled(reg))
        system.set_enabled(True, reg)
        self.assertTrue(system.is_enabled(reg))
        self.assertEqual(reg.values[system.VALUE_NAME], system.command())
        reg.values[system.VALUE_NAME] = '"C:\\Other\\app.exe"'
        self.assertFalse(system.is_enabled(reg), "another program's entry is not ours")
        system.set_enabled(False, reg)
        system.set_enabled(False, reg)
        self.assertFalse(system.is_enabled(reg))

    def test_unavailable_outside_the_installed_windows_app(self):
        with patch.object(system.sys, "platform", "linux"):
            self.assertFalse(system.available())
            self.assertFalse(system.is_enabled())
            with self.assertRaises(OSError):
                system.set_enabled(True)
            self.assertIn("Windows", system.reason())


if __name__ == "__main__":
    unittest.main()


class UpdateAtLaunch(unittest.TestCase):
    def test_off_by_default_and_only_true_turns_it_on(self):
        self.assertIs(data.OWNED["check_updates_on_launch"], False)
        self.assertIs(data.current({})["check_updates_on_launch"], False)
        self.assertIs(data.current({"check_updates_on_launch": 1})["check_updates_on_launch"], False)
        self.assertIs(data.current({"check_updates_on_launch": True})["check_updates_on_launch"], True)
        self.assertIn("check_updates_on_launch", data.EXPORT_KEYS)
