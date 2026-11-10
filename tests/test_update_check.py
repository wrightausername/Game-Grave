import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from gg_desktop import update_check as uc


def release(tag, created, size=1000, with_sum=True, setup=True):
    assets = []
    if setup:
        assets.append({"name": uc.SETUP_NAME, "size": size})
    if with_sum:
        assets.append({"name": uc.SUM_NAME, "size": 80})
    return {"tag_name": tag, "created_at": created, "assets": assets}


class Reply:
    def __init__(self, body):
        self.body = body

    def read(self, size=-1):
        return self.body


class UpdateCheckTests(unittest.TestCase):
    def test_newest_build_needs_installer_and_checksum(self):
        builds = [release("a", "2026-01-01"), release("b", "2026-03-01"), release("c", "2026-05-01", with_sum=False),
                  release("d", "2026-06-01", setup=False), release("e", "2026-07-01", size=10 ** 10), "junk", None]
        self.assertEqual(uc.newest_build(builds)["tag"], "b")
        self.assertIsNone(uc.newest_build([]))
        self.assertIsNone(uc.newest_build([{"assets": "no"}, {"assets": [None, 3]}]))

    def test_sentences_never_guess_which_build_is_installed(self):
        build = {"tag": "preview-run-9", "created": "x", "megabytes": 61.6}
        self.assertEqual(uc.describe(None, "")[0], "none")
        self.assertEqual(uc.describe(build, "preview-run-9")[0], "current")
        self.assertEqual(uc.describe(build, "preview-run-8")[0], "available")
        kind, words = uc.describe(build, "")
        self.assertEqual(kind, "unknown")
        self.assertIn("no record", words)

    def test_check_reads_the_list_and_state(self):
        body = json.dumps([release("preview-run-5", "2026-02-02")]).encode()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}, clear=False):
            (Path(folder) / "Game Grave Updater").mkdir()
            (Path(folder) / "Game Grave Updater" / "state.json").write_text('{"installed_tag": "preview-run-5"}')
            seen = {}

            def opener(url, headers):
                seen.update(url=url, headers=headers)
                return Reply(body)

            self.assertEqual(uc.check(opener)[0], "current")
            self.assertTrue(seen["url"].startswith("https://api.github.com/"))

    def test_bad_answers_become_readable_errors(self):
        for body in (b"not json", b"{}", b"\xff\xfe"):
            with self.assertRaises(uc.UpdateCheckError):
                uc.list_releases("", lambda url, headers, b=body: Reply(b))

        def refused(url, headers):
            raise urllib.error.HTTPError(url, 404, "no", {}, io.BytesIO())

        def offline(url, headers):
            raise urllib.error.URLError("no network")

        with self.assertRaises(uc.UpdateCheckError) as ctx:
            uc.list_releases("", refused)
        self.assertIn("token", str(ctx.exception))
        with self.assertRaises(uc.UpdateCheckError):
            uc.list_releases("", offline)

    def test_token_only_goes_in_the_header_and_state_is_tolerant(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}, clear=False):
            for name in ("GG_UPDATE_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
                os.environ.pop(name, None)
            self.assertEqual(uc.find_token(), "")
            self.assertEqual(uc.installed_tag(), "")
            (Path(folder) / "Game Grave Updater").mkdir()
            (Path(folder) / "Game Grave Updater" / "state.json").write_text("[1,2]")
            self.assertEqual(uc.installed_tag(), "")
            (Path(folder) / "Game Grave Updater" / "token.txt").write_text(" secret \n")
            self.assertEqual(uc.find_token(), "secret")
            seen = {}
            uc.list_releases("secret", lambda url, headers: seen.update(h=headers) or Reply(b"[]"))
            self.assertEqual(seen["h"]["Authorization"], "Bearer secret")

    def test_updater_path(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}, clear=False):
            self.assertIsNone(uc.updater_path(Path(folder)))
            (Path(folder) / uc.UPDATER_NAME).write_bytes(b"x")
            self.assertEqual(uc.updater_path(Path(folder)), Path(folder) / uc.UPDATER_NAME)


if __name__ == "__main__":
    unittest.main()
