import hashlib
import http.client
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "updater"))
import gg_updater as up  # noqa: E402


class Reply:
    def __init__(self, status=200, body=b"", headers=None):
        self.status, self.headers, self._body, self._pos = status, headers or {}, body, 0

    def read(self, n=-1):
        n = len(self._body) if n < 0 else n
        out = self._body[self._pos:self._pos + n]
        self._pos += len(out)
        return out


def release(tag, created, setup=True, checksum=True, size=100, draft=True):
    assets = []
    if setup:
        assets.append({"name": up.SETUP_NAME, "url": "https://api.github.com/a/1", "size": size})
    if checksum:
        assets.append({"name": up.SUM_NAME, "url": "https://api.github.com/a/2", "size": 90})
    return {"tag_name": tag, "name": tag, "created_at": created, "draft": draft, "assets": assets}


class PickRelease(unittest.TestCase):
    def test_newest_with_both_assets(self):
        found = up.pick_release([
            release("old", "2026-11-01T10:00:00Z"),
            release("new", "2026-11-09T10:00:00Z"),
            release("newest-but-no-setup", "2026-11-10T10:00:00Z", setup=False),
            release("newest-but-no-sum", "2026-11-11T10:00:00Z", checksum=False),
            "junk", None,
        ])
        self.assertEqual(found["tag"], "new")

    def test_rejects_bad_sizes_and_empty(self):
        self.assertIsNone(up.pick_release([]))
        self.assertIsNone(up.pick_release([release("x", "2026", size=0)]))
        self.assertIsNone(up.pick_release([release("x", "2026", size=10 ** 10)]))


class Checksum(unittest.TestCase):
    def test_parse(self):
        digest = "ab" * 32
        self.assertEqual(up.parse_sha256(f"{digest}  {up.SETUP_NAME}\n"), digest)
        self.assertEqual(up.parse_sha256(digest.upper() + " *" + up.SETUP_NAME), digest)
        for bad in ("", "nothex " * 3, "ab" * 10 + "  " + up.SETUP_NAME, f"{digest}  other.exe"):
            with self.assertRaises(up.UpdaterError):
                up.parse_sha256(bad)


class Status(unittest.TestCase):
    def test_messages(self):
        rel = up.pick_release([release("preview-run-5", "2026-11-09T10:00:00Z", size=50 * 1024 * 1024)])
        self.assertEqual(up.describe_status(None, "")[0], "none")
        self.assertEqual(up.describe_status(rel, "preview-run-5")[0], "current")
        self.assertEqual(up.describe_status(rel, "preview-run-4")[0], "available")
        self.assertEqual(up.describe_status(rel, "")[0], "available")


class Network(unittest.TestCase):
    def test_token_only_goes_to_api_and_redirect_drops_it(self):
        seen = []
        payload = b"setup-bytes"

        def opener(url, headers):
            seen.append((url, dict(headers)))
            if url.startswith("https://api.github.com/"):
                return Reply(302, headers={"Location": "https://objects.example.com/file?sig=1"})
            return Reply(200, payload)

        response = up._get("https://api.github.com/a/1", "SECRET", "application/octet-stream", opener)
        self.assertEqual(response.read(100), payload)
        self.assertEqual(seen[0][1].get("Authorization"), "Bearer SECRET")
        self.assertNotIn("Authorization", seen[1][1])

    def test_refuses_http_and_http_redirect(self):
        with self.assertRaises(up.UpdaterError):
            up._get("http://example.com/x", "", "x", lambda u, h: Reply())
        with self.assertRaises(up.UpdaterError):
            up._get("https://api.github.com/x", "", "x", lambda u, h: Reply(302, headers={"Location": "http://evil/x"}))

    def test_auth_errors_explain_the_token(self):
        def opener(url, headers):
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        with self.assertRaises(up.UpdaterError) as ctx:
            up._get("https://api.github.com/x", "", "x", opener)
        self.assertIn("token", str(ctx.exception))

    def test_list_releases_rejects_non_list(self):
        with self.assertRaises(up.UpdaterError):
            up.list_releases("", lambda u, h: Reply(200, b'{"message": "x"}'))
        self.assertEqual(up.list_releases("", lambda u, h: Reply(200, b"[]")), [])


class Dropped(unittest.TestCase):
    def test_a_connection_that_breaks_mid_answer_is_an_updater_error(self):
        class Breaks:
            status, headers = 200, {}

            def read(self, n=-1):
                raise http.client.IncompleteRead(b"partial")

        with self.assertRaises(up.UpdaterError):
            up.list_releases("", opener=lambda url, headers: Breaks())
        with self.assertRaises(up.UpdaterError):
            up.fetch_checksum({"sum": {"url": "https://api.github.com/a/2"}}, "", opener=lambda url, headers: Breaks())


class Download(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / "dl"
        self.body = os.urandom(300_000)
        self.rel = up.pick_release([release("t", "2026", size=len(self.body))])

    def tearDown(self):
        self.temp.cleanup()

    def opener(self, body):
        return lambda url, headers: Reply(200, body)

    def test_good_download_is_verified_and_named(self):
        steps = []
        path = up.download_setup(self.rel, "", self.folder, hashlib.sha256(self.body).hexdigest(),
                                 lambda d, t: steps.append((d, t)), self.opener(self.body))
        self.assertEqual(path.read_bytes(), self.body)
        self.assertEqual(steps[-1], (len(self.body), len(self.body)))
        self.assertEqual([p.name for p in self.folder.iterdir()], [up.SETUP_NAME])

    def test_wrong_hash_wrong_size_leave_nothing(self):
        good = hashlib.sha256(self.body).hexdigest()
        for body, digest in ((self.body[:-1] + b"X", good), (self.body[:-5], good), (self.body + b"extra", good)):
            with self.assertRaises(up.UpdaterError):
                up.download_setup(self.rel, "", self.folder, digest, None, self.opener(body))
            self.assertEqual(list(self.folder.iterdir()), [], "a rejected download must not stay on disk")


class Files(unittest.TestCase):
    def test_state_and_token_round_trip(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LOCALAPPDATA": temp}, clear=False):
            for name in ("GG_UPDATE_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
                os.environ.pop(name, None)
            self.assertEqual(up.read_state(), {})
            up.write_state(installed_tag="preview-run-9")
            self.assertEqual(up.read_state()["installed_tag"], "preview-run-9")
            self.assertEqual(up.find_token(), "")
            up.save_token(" abc \n")
            self.assertEqual(up.find_token(), "abc")
            os.environ["GG_UPDATE_TOKEN"] = "env"
            self.assertEqual(up.find_token(), "env")

    def test_fetch_command_writes_a_result_file(self):
        body = os.urandom(5000)
        digest = hashlib.sha256(body).hexdigest()
        rels = [release("preview-run-7", "2026-11-09T10:00:00Z", size=len(body))]

        def opener(url, headers):
            if "releases" in url:
                return Reply(200, json.dumps(rels).encode())
            if url.endswith("/a/2"):
                return Reply(200, f"{digest}  {up.SETUP_NAME}\n".encode())
            return Reply(200, body)

        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "result.json"
            with patch.object(up, "_real_open", opener):
                self.assertEqual(up.run_fetch(Path(temp) / "dl", out), 0)
            data = json.loads(out.read_text())
            self.assertTrue(data["ok"])
            self.assertEqual((data["tag"], data["bytes"]), ("preview-run-7", len(body)))
            with patch.object(up, "_real_open", lambda u, h: Reply(200, b"[]")):
                self.assertEqual(up.run_fetch(Path(temp) / "dl2", out), 1)
            self.assertFalse(json.loads(out.read_text())["ok"])


if __name__ == "__main__":
    unittest.main()
