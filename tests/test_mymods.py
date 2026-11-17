"""My Mods: MO2 profile reading, snapshot-and-undo writes, Mod Doctor, Steam Workshop names."""
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from gg_desktop import mymods_core as mc
from gg_desktop import mymods_doctor as doctor
from gg_desktop import workshop_core as ws


def plugin(path: Path, masters=()):
    body = b"".join(b"MAST" + struct.pack("<H", len(m) + 1) + m.encode() + b"\0" + b"DATA\x08\x00" + b"\0" * 8
                    for m in masters)
    path.write_bytes(b"TES4" + struct.pack("<I", len(body)) + b"\0" * 16 + body)


def instance(tmp: Path, modlist: str, mods=None, plugins_txt="*Skyrim.esm\n"):
    (tmp / "profiles" / "Main").mkdir(parents=True)
    (tmp / "mods").mkdir()
    (tmp / "ModOrganizer.ini").write_text("[General]\ngameName=SkyrimSE\nselected_profile=@ByteArray(Main)\n"
                                          "[Settings]\n", encoding="utf-8")
    (tmp / "profiles" / "Main" / "modlist.txt").write_text(modlist, encoding="utf-8")
    (tmp / "profiles" / "Main" / "plugins.txt").write_text(plugins_txt, encoding="utf-8")
    for name, files in (mods or {}).items():
        folder = tmp / "mods" / name
        folder.mkdir()
        for rel, content in files.items():
            target = folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if callable(content):
                content(target)
            else:
                target.write_text(content, encoding="utf-8")
    return mc.read_instance(tmp / "ModOrganizer.ini")


MODLIST = "# header\n+High Priority\n-Turned Off\n+Low Priority\n*DLC: Dawnguard\n"


class Reading(unittest.TestCase):
    def test_order_and_meta(self):
        tmp = Path(tempfile.mkdtemp())
        inst = instance(tmp, MODLIST, {"High Priority": {"meta.ini": "[General]\nmodid=266\nversion=4.3.1\n"
                                                                       "newestVersion=4.3.2\ngameName=SkyrimSE\n"},
                                       "Turned Off": {}, "Low Priority": {}})
        self.assertEqual(inst.selected, "Main")
        prof = mc.read_profile(inst, "Main")
        self.assertEqual([m.name for m in prof.mods], ["DLC: Dawnguard", "Low Priority", "Turned Off", "High Priority"])
        high = prof.mods[-1]
        self.assertEqual((high.version, high.newest, high.nexus_id), ("4.3.1", "4.3.2", "266"))
        self.assertTrue(high.update)
        self.assertFalse(prof.mods[2].enabled)
        self.assertEqual(prof.mods[0].kind, "base")

    def test_round_trip_keeps_mo2_order(self):
        rows = mc.parse_modlist(MODLIST)
        self.assertEqual(mc.parse_modlist(mc.render_modlist(rows)), rows)


class Writes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.inst = instance(self.tmp, MODLIST, {"High Priority": {}, "Turned Off": {}, "Low Priority": {}})
        self.folder = self.tmp / "profiles" / "Main"
        self.snaps = self.tmp / "snaps"

    def names_on(self):
        return {m.name for m in mc.read_profile(self.inst, "Main").mods if m.enabled}

    def test_turn_on_then_undo(self):
        before = (self.folder / "modlist.txt").read_text()
        mc.set_enabled(self.folder, ["Turned Off"], True, running=False, root=self.snaps)
        self.assertIn("Turned Off", self.names_on())
        self.assertEqual(len(mc.snapshots(self.folder, self.snaps)), 1)
        mc.undo(self.folder, running=False, root=self.snaps)
        self.assertEqual((self.folder / "modlist.txt").read_text(), before)
        self.assertEqual(mc.snapshots(self.folder, self.snaps), [])

    def test_move_changes_priority(self):
        mc.move(self.folder, "Low Priority", 3, running=False, root=self.snaps)
        order = [m.name for m in mc.read_profile(self.inst, "Main").mods]
        self.assertEqual(order[-1], "Low Priority")
        self.assertTrue((self.folder / "modlist.txt").read_text().splitlines()[1].endswith("Low Priority"))

    def test_refuses_while_mo2_runs_and_unknown_mods(self):
        with self.assertRaises(mc.ModsError):
            mc.set_enabled(self.folder, ["Turned Off"], True, running=True, root=self.snaps)
        with self.assertRaises(mc.ModsError):
            mc.set_enabled(self.folder, ["Nope"], True, running=False, root=self.snaps)
        self.assertEqual(mc.snapshots(self.folder, self.snaps), [])

    def test_undo_leaves_outside_edits_alone(self):
        mc.set_enabled(self.folder, ["Turned Off"], True, running=False, root=self.snaps)
        (self.folder / "modlist.txt").write_text("+Something Else\n")
        with self.assertRaises(mc.ModsError):
            mc.undo(self.folder, running=False, root=self.snaps)
        self.assertEqual((self.folder / "modlist.txt").read_text(), "+Something Else\n")

    def test_reorder_must_match(self):
        with self.assertRaises(mc.ModsError):
            mc.reorder(self.folder, ["High Priority"], running=False, root=self.snaps)


class Doctor(unittest.TestCase):
    def test_finds_master_in_off_mod_updates_and_clash(self):
        tmp = Path(tempfile.mkdtemp())
        mods = {"Armors": {"Armors.esp": lambda p: plugin(p, ["Skyrim.esm", "SkyUI_SE.esp"]),
                           "textures/iron.dds": "a", "meta.ini": "[General]\nmodid=5\nversion=1.0\nnewestVersion=1.2\n"},
                "SkyUI": {"SkyUI_SE.esp": lambda p: plugin(p, ["Skyrim.esm"])},
                "Retex": {"textures/iron.dds": "b"},
                "Broken": {"Broken.esp": lambda p: plugin(p, ["Missing.esm"])}}
        inst = instance(tmp, "+Retex\n+Broken\n-SkyUI\n+Armors\n+Gone\n", mods)
        prof = mc.read_profile(inst, "Main")
        report = doctor.diagnose(inst, prof, base_plugins=set())
        kinds = {f.kind for f in report.findings}
        self.assertTrue({"needs_mod_on", "missing_master", "update", "clash", "folder_missing"} <= kinds, kinds)
        on = report.of("needs_mod_on")[0]
        self.assertEqual((on.fix, on.fix_mods), ("turn_on", ("SkyUI",)))
        self.assertIn("Missing.esm", report.of("missing_master")[0].title)
        self.assertEqual(report.clashes[0][:2], ("Retex", "Armors"))   # Retex is lower in the list, so it wins
        self.assertIn("nexusmods.com/skyrimspecialedition/mods/5", report.of("update")[0].url)
        sentence, tone = doctor.status_line(report)
        self.assertTrue(sentence.startswith("3 things need you"), sentence)
        self.assertEqual(tone, "warn")

    def test_healthy(self):
        tmp = Path(tempfile.mkdtemp())
        inst = instance(tmp, "+A\n", {"A": {"a.txt": "x"}})
        report = doctor.diagnose(inst, mc.read_profile(inst, "Main"), base_plugins=set())
        self.assertEqual(doctor.status_line(report), ("Your mods look healthy. Nothing needs you right now.", "good"))

    def test_masters_read_from_header(self):
        p = Path(tempfile.mkdtemp()) / "x.esp"
        plugin(p, ["Skyrim.esm", "Update.esm"])
        self.assertEqual(mc.plugin_masters(p), ["Skyrim.esm", "Update.esm"])


class Workshop(unittest.TestCase):
    def library(self):
        lib = Path(tempfile.mkdtemp())
        content = lib / "steamapps" / "workshop" / "content" / "255710"
        for item in ("111", "222"):
            (content / item).mkdir(parents=True)
        (lib / "steamapps" / "workshop" / "appworkshop_255710.acf").write_text(
            '"AppWorkshop"\n{\n "WorkshopItemsInstalled"\n {\n  "111"\n  {\n   "size" "1000"\n   "timeupdated" "100"\n  }\n'
            '  "222"\n  {\n   "size" "50"\n   "timeupdated" "500"\n  }\n }\n}\n', encoding="utf-8")
        return lib

    def test_items_and_names(self):
        lib = self.library()
        items = ws.local_items([lib], "255710")
        self.assertEqual([(i.item_id, i.size, i.installed_updated) for i in items], [("111", 1000, 100), ("222", 50, 500)])
        self.assertEqual(ws.workshop_games([lib]), ["255710"])
        answer = json.dumps({"response": {"publishedfiledetails": [
            {"publishedfileid": "111", "result": 1, "title": "Better Roads", "preview_url": "https://images.steamusercontent.com/x.jpg",
             "time_updated": 200, "file_size": 1000, "tags": [{"tag": "Roads"}]},
            {"publishedfileid": "222", "result": 9}]}})
        calls = []
        cache = ws.refresh_names(items, {}, fetch=lambda ids: calls.append(ids) or ws.parse_details(answer), now=1000)
        named = ws.with_names(items, cache)
        self.assertEqual(named[0].name, "Better Roads")
        self.assertTrue(named[0].update_waiting)
        self.assertTrue(named[1].removed and named[1].name == "Workshop item 222")
        self.assertEqual(calls, [["111", "222"]])
        ws.refresh_names(items, cache, fetch=lambda ids: self.fail("cached names are not asked again"), now=2000)
        self.assertTrue(ws.preview_allowed(named[0].preview))
        self.assertFalse(ws.preview_allowed("https://evil.example/x.jpg"))

    def test_request_shape(self):
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def opener(request, timeout=None):
            seen["url"], seen["body"] = request.full_url, request.data.decode()
            return Resp(b'{"response":{"publishedfiledetails":[]}}')
        ws.fetch_details(["111", "222"], opener=opener)
        self.assertEqual(seen["url"], ws.API)
        self.assertIn("itemcount=2", seen["body"])
        self.assertIn("publishedfileids%5B1%5D=222", seen["body"])


if __name__ == "__main__":
    unittest.main()


class LockedFile(unittest.TestCase):
    def test_replace_falls_back_to_writing_in_place(self):
        from unittest.mock import patch
        tmp = Path(tempfile.mkdtemp())
        target, temp = tmp / "modlist.txt", tmp / "modlist.txt.gg-tmp"
        target.write_text("old old old\n")
        temp.write_text("new\n")
        with patch("gg_desktop.mymods_core.os.replace", side_effect=PermissionError("locked")):
            mc._replace(temp, target, tries=2, wait=0)
        self.assertEqual(target.read_text(), "new\n")
        self.assertFalse(temp.exists())
