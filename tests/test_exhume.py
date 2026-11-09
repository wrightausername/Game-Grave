import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from gg_desktop import exhume_core as ex

STORE = """Microsoft PnP Utility

Published Name:     oem3.inf
Original Name:      prnms009.inf
Provider Name:      Microsoft
Class Name:         Printers
Class GUID:         {4d36e979-e325-11ce-bfc1-08002be10318}
Driver Version:     06/21/2006 10.0.19041.1
Signer Name:        Microsoft Windows

Published Name:     oem42.inf
Original Name:      nv_dispi.inf
Provider Name:      NVIDIA
Class Name:         Display
Class GUID:         {4d36e968-e325-11ce-bfc1-08002be10318}
Driver Version:     10/05/2024 32.0.15.6614
Signer Name:        Microsoft Windows Hardware Compatibility Publisher

Published Name:     oem40.inf
Original Name:      nv_dispi.inf
Provider Name:      NVIDIA
Class Name:         Display
Class GUID:         {4d36e968-e325-11ce-bfc1-08002be10318}
Driver Version:     08/12/2024 32.0.15.6094
Signer Name:        Microsoft Windows Hardware Compatibility Publisher

Published Name:     oem31.inf
Original Name:      nv_dispi.inf
Provider Name:      NVIDIA
Class Name:         Display
Class GUID:         {4d36e968-e325-11ce-bfc1-08002be10318}
Driver Version:     03/01/2024 31.0.15.5222
Signer Name:        Microsoft Windows Hardware Compatibility Publisher

Published Name:     oem12.inf
Original Name:      iigd_dch.inf
Provider Name:      Intel Corporation
Class Name:         Display
Class GUID:         {4d36e968-e325-11ce-bfc1-08002be10318}
Driver Version:     01/10/2024 31.0.101.5333
Signer Name:        Microsoft Windows Hardware Compatibility Publisher
"""
# Same records with German labels and a day-first date: parsing goes by values, not labels.
GERMAN = (STORE.replace("Published Name", "Veröffentlichter Name").replace("Original Name", "Originalname")
          .replace("Provider Name", "Anbietername").replace("Class Name", "Klassenname")
          .replace("Class GUID", "Klassen-GUID").replace("Driver Version", "Treiberversion")
          .replace("Signer Name", "Signaturgebername").replace("10/05/2024", "05.10.2024"))
CURRENT = json.dumps([{"DeviceName": "NVIDIA GeForce RTX 4070", "DriverVersion": "32.0.15.6614", "InfName": "oem42.inf",
                       "DriverProviderName": "NVIDIA", "Date": "2024-10-05"}])


def cards(marks=None):
    return ex.build_cards(ex.parse_current(CURRENT), ex.parse_store(STORE), marks or {})


class ExhumeTests(unittest.TestCase):
    def test_store_keeps_only_display_packages_and_reads_values(self):
        packages = ex.parse_store(STORE)
        self.assertEqual([p.published for p in packages], ["oem42.inf", "oem40.inf", "oem31.inf", "oem12.inf"])
        self.assertEqual(packages[0].version, "32.0.15.6614")
        self.assertEqual(packages[0].provider, "NVIDIA")
        self.assertEqual([p.published for p in ex.parse_store(GERMAN)], [p.published for p in packages])
        self.assertEqual(ex.parse_store("junk: text\nmore: lines"), [])

    def test_current_parse_handles_one_object_and_junk(self):
        self.assertEqual(ex.parse_current(CURRENT)[0].inf, "oem42.inf")
        self.assertEqual(len(ex.parse_current(json.dumps({"DeviceName": "X", "InfName": "oem1.inf"}))), 1)
        self.assertEqual(ex.parse_current("not json"), [])
        self.assertEqual(ex.parse_current(""), [])

    def test_older_drivers_are_the_same_makers_and_older(self):
        card = cards()[0]
        self.assertEqual([p.published for p in card.older], ["oem40.inf", "oem31.inf"])
        self.assertEqual(card.reason, "")

    def test_cards_explain_why_rollback_is_not_offered(self):
        builtin = ex.Current("Microsoft Basic Display Adapter", "10.0.1", "display.inf", "Microsoft", "")
        self.assertIn("built-in", ex.build_cards([builtin], [], {})[0].reason)
        lonely = ex.Current("Intel", "31.0.101.5333", "oem12.inf", "Intel Corporation", "")
        self.assertIn("No older driver", ex.build_cards([lonely], ex.parse_store(STORE), {})[0].reason)

    def test_marks_round_trip_and_ignore_junk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ex.save_mark("GPU", "32.0.15.6094", root, datetime(2026, 11, 9))
            self.assertEqual(ex.load_marks(root), {"GPU": {"version": "32.0.15.6094", "marked": "2026-11-09"}})
            (root / "marks.json").write_text('{"a": 5, "b": {"version": 3}}', encoding="utf-8")
            self.assertEqual(ex.load_marks(root), {})
            (root / "marks.json").write_text("garbage", encoding="utf-8")
            self.assertEqual(ex.load_marks(root), {})
        card = cards({"NVIDIA GeForce RTX 4070": {"version": "32.0.15.6614", "marked": "x"}})[0]
        self.assertTrue(card.current_is_marked)

    def test_plan_names_exact_commands_and_refuses_bad_targets(self):
        card = cards()[0]
        plan = ex.plan_rollback(card, card.older[0])
        self.assertEqual(plan[0], ["pnputil", "/delete-driver", "oem42.inf", "/uninstall", "/force"])
        self.assertEqual(plan[1][:2], ["pnputil", "/add-driver"])
        self.assertTrue(plan[1][2].endswith("oem40.inf") and plan[1][3] == "/install")
        newer = ex.Package("oem50.inf", "nv_dispi.inf", "NVIDIA", "99.0.0.1", "01/01/2030")
        with self.assertRaises(ValueError):
            ex.plan_rollback(card, newer)
        evil = ex.Package("oem40.inf & calc", "x", "NVIDIA", "1.0", "")
        card.older.append(evil)
        with self.assertRaises(ValueError):
            ex.plan_rollback(card, evil)

    def test_rollback_needs_admin_and_runs_nothing_without(self):
        card, ran = cards()[0], []
        out = ex.rollback(card, card.older[0], run=ran.append, log=lambda *a, **k: None, admin=False)
        self.assertFalse(out.ok)
        self.assertIn("Nothing was changed", out.message)
        self.assertEqual(ran, [])

    def test_rollback_runs_both_steps_and_logs(self):
        card, ran, logged = cards()[0], [], []
        out = ex.rollback(card, card.older[0], run=lambda c: ran.append(c) or "ok", admin=True,
                          log=lambda kind, details, **kw: logged.append((kind, details, kw)))
        self.assertTrue(out.ok)
        self.assertEqual(len(ran), 2)
        self.assertEqual(logged[0][0], "exhume_rollback")
        self.assertEqual(logged[0][2]["result"], "completed")
        self.assertIn("32.0.15.6614 to 32.0.15.6094", logged[0][1])

    def test_failure_on_first_step_changes_nothing_and_second_step_warns(self):
        card = cards()[0]
        calls = []

        def first_fails(command):
            calls.append(command)
            raise OSError("Access is denied.")
        logged = []
        out = ex.rollback(card, card.older[0], run=first_fails, admin=True, log=lambda *a, **k: logged.append(k))
        self.assertFalse(out.ok)
        self.assertEqual(len(calls), 1)
        self.assertIn("Nothing was changed", out.message)
        self.assertEqual(logged[0]["result"], "failed")

        def second_fails(command):
            if "/add-driver" in command:
                raise OSError("The driver could not be installed.")
            return "removed"
        out = ex.rollback(card, card.older[0], run=second_fails, admin=True, log=lambda *a, **k: None)
        self.assertFalse(out.ok)
        self.assertIn("current driver package was removed", out.message)

    def test_default_logger_writes_the_real_activity_log(self):
        import core
        card = cards()[0]
        with tempfile.TemporaryDirectory() as temp, patch("core.config_dir", return_value=Path(temp)):
            ex.rollback(card, card.older[0], run=lambda c: "ok", admin=True)
            self.assertEqual([e["kind"] for e in core.get_activity()], ["exhume_rollback"])

    @unittest.skipUnless(os.name == "nt", "reads the real Windows driver store")
    def test_real_windows_output_parses(self):
        packages = ex.parse_store(ex.query_store())
        for p in packages:
            self.assertRegex(p.published, r"(?i)^oem\d+\.inf$")
            self.assertTrue(p.version)
        current = ex.parse_current(ex.query_current())
        self.assertIsInstance(current, list)


if __name__ == "__main__":
    unittest.main()
