import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from gg_desktop import nexus_core as nx


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def opener_for(routes, seen=None):
    def open_(request, timeout=0):
        url = request.full_url
        if seen is not None:
            seen.append((url, dict(request.header_items())))
        for part, answer in routes.items():
            if part in url:
                if isinstance(answer, int):
                    raise urllib.error.HTTPError(url, answer, "x", {}, None)
                data = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
                return Response(data)
        raise urllib.error.URLError("no route")
    return open_


KEY = "abcdEFGH1234567890abcdEFGH1234567890"


class Nexus(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_references_are_strict(self):
        self.assertEqual(nx.clean_ref("SkyrimSpecialEdition/266"), "skyrimspecialedition/266")
        for bad in ("", "../../x/1", "game/abc", "game/1/2", "a b/1", "game/12345678901"):
            self.assertEqual(nx.clean_ref(bad), "")
        self.assertIsNone(nx.mod_page("nonsense"))

    def test_meta_ini_needs_a_real_modid(self):
        good = self.root / "a.ini"
        good.write_text("[General]\ngameName=fallout4\nmodid=55\n")
        zero = self.root / "b.ini"
        zero.write_text("[General]\nmodid=0\n")
        self.assertEqual(nx.read_meta(good), "fallout4/55")
        self.assertEqual(nx.read_meta(zero), "")
        self.assertEqual(nx.read_meta(self.root / "missing.ini"), "")

    def test_key_is_saved_loaded_and_forgotten(self):
        fake = lambda data, protect: data[::-1]
        how = nx.save_key(KEY, self.root, protector=fake)
        self.assertEqual(how, "windows")
        self.assertNotIn(KEY, nx.key_path(self.root).read_text())
        self.assertEqual(nx.load_key(self.root, protector=fake), KEY)
        self.assertTrue(nx.forget_key(self.root))
        self.assertEqual(nx.load_key(self.root, protector=fake), "")
        with self.assertRaises(nx.NexusError):
            nx.save_key("short", self.root)

    def test_a_key_that_windows_cannot_protect_is_not_saved_in_the_clear(self):
        def broken(data, protect):
            raise OSError("no")
        with self.assertRaises(nx.NexusError):
            nx.save_key(KEY, self.root, protector=broken)
        self.assertFalse(nx.key_path(self.root).exists())

    def test_validate_reports_name_and_premium_and_sends_the_key_only_to_nexus(self):
        seen = []
        account = nx.validate(KEY, opener_for({"validate.json": {"name": "Alex", "is_premium": True}}, seen))
        self.assertEqual((account.name, account.premium), ("Alex", True))
        self.assertTrue(seen[0][0].startswith("https://api.nexusmods.com/"))
        self.assertEqual(seen[0][1]["Apikey"], KEY)
        free = nx.validate(KEY, opener_for({"validate.json": {"name": "Sam", "is_premium": False}}))
        self.assertFalse(free.premium)

    def test_errors_are_plain_words(self):
        for code, word in ((401, "did not accept"), (429, "too many requests"), (404, "no such mod")):
            with self.assertRaises(nx.NexusError) as caught:
                nx.validate(KEY, opener_for({"validate.json": code}))
            self.assertIn(word, str(caught.exception))
        with self.assertRaises(nx.NexusError) as caught:
            nx.validate(KEY, opener_for({}))
        self.assertIn("Could not reach", str(caught.exception))

    def test_main_file_prefers_primary_then_newest(self):
        files = {"files": [{"file_id": 1, "file_name": "old.zip", "uploaded_timestamp": 10},
                           {"file_id": 2, "file_name": "new.zip", "uploaded_timestamp": 20},
                           {"file_id": 3, "file_name": "primary.zip", "uploaded_timestamp": 5, "is_primary": True}]}
        pick = nx.main_file("skyrim/1", KEY, opener_for({"files.json": files}))
        self.assertEqual((pick.file_id, pick.name), (3, "primary.zip"))
        del files["files"][2]
        self.assertEqual(nx.main_file("skyrim/1", KEY, opener_for({"files.json": files})).file_id, 2)
        with self.assertRaises(nx.NexusError):
            nx.main_file("skyrim/1", KEY, opener_for({"files.json": {"files": []}}))

    def test_download_link_only_from_trusted_hosts_and_free_accounts_get_a_plain_message(self):
        good = [{"URI": "https://cf-files.nexus-cdn.com/a/b.zip"}]
        self.assertEqual(nx.download_url("g/1", 2, KEY, opener_for({"download_link.json": good})), good[0]["URI"])
        with self.assertRaises(nx.NexusError):
            nx.download_url("g/1", 2, KEY, opener_for({"download_link.json": [{"URI": "https://evil.example/x.zip"}]}))
        with self.assertRaises(nx.NexusError) as caught:
            nx.download_url("g/1", 2, KEY, opener_for({"download_link.json": 403}))
        self.assertIn("Premium", str(caught.exception))
        self.assertFalse(nx.trusted_host("http://x.nexus-cdn.com/a"))
        self.assertFalse(nx.trusted_host("https://nexus-cdn.com.evil.example/a"))

    def test_download_never_overwrites_cleans_up_and_caps_size(self):
        url = "https://cf-files.nexus-cdn.com/a.zip"
        folder = self.root / "downloads"
        first = nx.download(url, folder, "Mod.zip", opener=opener_for({"nexus-cdn": b"A" * 1000}))
        second = nx.download(url, folder, "Mod.zip", opener=opener_for({"nexus-cdn": b"B" * 1000}))
        self.assertEqual(first.name, "Mod.zip")
        self.assertEqual(second.name, "Mod (2).zip")
        self.assertEqual(first.read_bytes(), b"A" * 1000)
        with self.assertRaises(nx.NexusError):
            nx.download(url, folder, "Big.zip", expected_kb=1, opener=opener_for({"nexus-cdn": b"C" * (60 * 1024 * 1024)}))
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["Mod (2).zip", "Mod.zip"])
        with self.assertRaises(nx.NexusError):
            nx.download("https://evil.example/a.zip", folder, "x.zip", opener=opener_for({}))
        self.assertEqual(nx.safe_name("../../Windows/evil.exe"), "evil.exe")

    def test_downloads_folder_uses_the_mo2_setting_or_a_game_grave_folder(self):
        inst = self.root / "inst"
        inst.mkdir()
        (inst / "ModOrganizer.ini").write_text("[Settings]\ndownload_directory=%BASE_DIR%/my-downloads\n")
        self.assertEqual(nx.downloads_folder(inst, self.root / "fallback"), inst / "my-downloads")
        (inst / "ModOrganizer.ini").write_text("[Settings]\n")
        self.assertEqual(nx.downloads_folder(inst, self.root / "fallback"), inst / "downloads")
        self.assertEqual(nx.downloads_folder(None, self.root / "fallback"), self.root / "fallback")


if __name__ == "__main__":
    unittest.main()
