"""Graphics driver comparison with the card maker, and firmware facts. No network: answers are faked."""
import io
import json
import unittest
from datetime import date

from gg_desktop import upkeep_vendor as v

PRODUCTS = """<?xml version="1.0"?><LookupValueSearch><LookupValues>
<LookupValue ParentID="120"><Name>GeForce RTX 3060 Ti</Name><Value>934</Value></LookupValue>
<LookupValue ParentID="123"><Name>NVIDIA GeForce RTX 3060 Ti Laptop GPU</Name><Value>970</Value></LookupValue>
<LookupValue ParentID="127"><Name>GeForce RTX 4090</Name><Value>995</Value></LookupValue>
</LookupValues></LookupValueSearch>"""
LOOKUP = json.dumps({"Success": "1", "IDS": [{"downloadInfo": {"Version": "566.36", "ReleaseDateTime": "Thu Dec 05, 2024",
                                                                 "Name": "GeForce%20Game%20Ready%20Driver"}}]})


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener(routes):
    def open_(request, timeout=None):
        for key, value in routes.items():
            if key in request.full_url:
                return Resp(value.encode())
        raise OSError("no route")
    return open_


class Versions(unittest.TestCase):
    def test_nvidia_form(self):
        self.assertEqual(v.nvidia_version("32.0.15.6094"), "560.94")
        self.assertEqual(v.nvidia_version("31.0.15.5222"), "552.22")
        self.assertEqual(v.nvidia_version("32.0.15.6614"), "566.14")
        self.assertEqual(v.nvidia_version("bad"), "")

    def test_compare(self):
        self.assertTrue(v.newer("566.36", "560.94"))
        self.assertFalse(v.newer("560.94", "560.94"))
        self.assertIsNone(v.newer("", "560.94"))

    def test_makers(self):
        self.assertEqual(v.maker_of("NVIDIA GeForce RTX 3060 Ti"), "NVIDIA")
        self.assertEqual(v.maker_of("AMD Radeon RX 7800 XT"), "AMD")
        self.assertEqual(v.maker_of("Intel(R) Arc(TM) A770 Graphics"), "Intel")


class Nvidia(unittest.TestCase):
    def test_ids_desktop_and_laptop(self):
        self.assertEqual(v.nvidia_ids("NVIDIA GeForce RTX 3060 Ti", PRODUCTS), ("120", "934"))
        self.assertEqual(v.nvidia_ids("NVIDIA GeForce RTX 3060 Ti Laptop GPU", PRODUCTS), ("123", "970"))
        with self.assertRaises(v.VendorError):
            v.nvidia_ids("NVIDIA GeForce RTX 9999", PRODUCTS)

    def test_newer_driver_found(self):
        check = v.check_graphics("NVIDIA GeForce RTX 3060 Ti", "32.0.15.6094", "2024-09-12",
                                 opener({"lookupValueSearch": PRODUCTS, "AjaxDriverService": LOOKUP}))
        self.assertEqual((check.installed, check.latest, check.latest_date), ("560.94", "566.36", "2024-12-05"))
        self.assertTrue(check.outdated)
        self.assertIn("newer driver: 566.36", check.summary)
        self.assertIn("psid=120&pfid=934", v.NVIDIA_LOOKUP.format(psid=120, pfid=934))

    def test_unreachable_is_said_not_guessed(self):
        check = v.check_graphics("NVIDIA GeForce RTX 3060 Ti", "32.0.15.6094", "", opener({}))
        self.assertIsNone(check.outdated)
        self.assertIn("Couldn't read NVIDIA's newest version", check.note)

    def test_only_maker_hosts(self):
        with self.assertRaises(v.VendorError):
            v._get("https://example.com/x")


AMD_REAL = json.dumps({"ADDL_VERSION": "1.0 Consumer_beta_Win10_productionASICs", "DLL_URL": "NA",
                       "Consumer_Whql_Win10": {"version": "26.20.15.07-261015a-205306C-AMD-Software-Adrenalin-Edition",
                                               "url": "https://www2.ati.com/x.json"},
                       "Consumer_Beta_Win10": {"version": "26.20.15.12-261023a1-205499C-AMD-Software-Adrenalin-Edition"}})


class Amd(unittest.TestCase):
    def test_real_file_layout_compares_build_dates(self):
        self.assertEqual(v.parse_amd_whql(AMD_REAL), ("26.20.15.07", "2026-10-15"))
        old = v.check_graphics("AMD Radeon RX 7800 XT", "32.0.21045.5002", "2026-05-01", opener({"drivers.amd.com": AMD_REAL}))
        self.assertTrue(old.outdated)
        self.assertIn("built 2026-10-15", old.summary)
        same = v.check_graphics("AMD Radeon RX 7800 XT", "32.0.32015.7001", "2026-10-10", opener({"drivers.amd.com": AMD_REAL}))
        self.assertFalse(same.outdated)
        undated = v.check_graphics("AMD Radeon RX 7800 XT", "32.0.32015.7001", "", opener({"drivers.amd.com": AMD_REAL}))
        self.assertIsNone(undated.outdated)
        self.assertIn("26.20.15.07", undated.note)

    def test_version_file_with_store_version(self):
        text = json.dumps({"releases": [{"version": "24.12.1", "driverStoreVersion": "32.0.12033.1030"},
                                        {"version": "25.1.1", "driverStoreVersion": "32.0.13031.3015"}]})
        self.assertEqual(v.parse_amd(text), ("25.1.1", "32.0.13031.3015"))
        check = v.check_graphics("AMD Radeon RX 7800 XT", "32.0.12033.1030", "", opener({"drivers.amd.com": text}))
        self.assertTrue(check.outdated)
        self.assertEqual(check.latest_name, "Adrenalin 25.1.1")

    def test_version_only(self):
        check = v.check_graphics("AMD Radeon RX 7800 XT", "32.0.12033.1030", "",
                                 opener({"drivers.amd.com": json.dumps({"Version": "25.1.1"})}))
        self.assertIsNone(check.outdated)
        self.assertIn("25.1.1", check.note)

    def test_intel_is_honest(self):
        check = v.check_graphics("Intel(R) Arc(TM) A770 Graphics", "32.0.101.6299", "2024-11-01")
        self.assertIsNone(check.outdated)
        self.assertIn("Intel doesn't publish", check.note)


class Firmware(unittest.TestCase):
    def test_parse_and_hints(self):
        facts = v.parse_firmware(json.dumps({"BiosVersion": "F12", "BiosDate": "2021-03-04", "BoardMaker": "Gigabyte Technology Co., Ltd.",
                                             "Board": "B550 AORUS ELITE", "PcMaker": "To Be Filled By O.E.M.",
                                             "PcModel": "System Product Name",
                                             "Drives": [{"Model": "Samsung SSD 980 PRO 1TB", "Firmware": "5B2QGXA7"},
                                                        {"Model": "WDC WDS100T2B0A", "Firmware": "411030WD"}]}))
        self.assertEqual(facts.model, "Gigabyte Technology Co., Ltd. B550 AORUS ELITE")
        self.assertEqual(facts.support[0], "GIGABYTE support")
        self.assertGreater(facts.bios_age(date(2026, 11, 11)), 5)
        self.assertEqual(facts.drives[0][2], "Samsung Magician")
        self.assertEqual(v.drive_tool("Crucial CT1000P5PSSD8"), "Crucial Storage Executive")

    def test_prebuilt_uses_pc_model(self):
        facts = v.parse_firmware(json.dumps({"BiosVersion": "1.20.0", "PcMaker": "Dell Inc.", "PcModel": "XPS 8960",
                                             "BoardMaker": "Dell Inc.", "Board": "0X8DXD", "Drives": {"Model": "x"}}))
        self.assertEqual(facts.model, "Dell Inc. XPS 8960")
        self.assertEqual(facts.support[0], "Dell support")
        self.assertEqual(len(facts.drives), 1)


if __name__ == "__main__":
    unittest.main()
