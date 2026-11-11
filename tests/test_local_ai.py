"""Optional local AI model: verified downloads, safe unpacking, the server wrapper, and the reply rules."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from gg_desktop import assistant_engine as engine
from gg_desktop import local_ai_core as ai
from gg_desktop import local_ai_prompt as prompt
from tests.test_assistant import facts


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOpener:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def open(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        value = self.routes[url]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, (dict, list)):
            value = json.dumps(value).encode()
        return FakeResponse(value)


class Hosts(unittest.TestCase):
    def test_only_official_https_hosts(self):
        self.assertTrue(ai.host_allowed("https://huggingface.co/ggml-org/x/resolve/main/a.gguf"))
        self.assertTrue(ai.host_allowed("https://cas-bridge.xethub.hf.co/x"))
        self.assertTrue(ai.host_allowed("https://release-assets.githubusercontent.com/x"))
        self.assertFalse(ai.host_allowed("http://huggingface.co/x"))
        self.assertFalse(ai.host_allowed("https://huggingface.co.evil.com/x"))
        self.assertFalse(ai.host_allowed("https://example.com/x"))

    def test_models_are_open_licensed_official_repos(self):
        self.assertEqual([m.key for m in ai.MODELS], ["small", "medium", "large"])
        for m in ai.MODELS:
            self.assertTrue(m.repo.startswith("ggml-org/Qwen3-"), m.repo)


class Resolve(unittest.TestCase):
    SHA = "a" * 64

    def test_model_file_and_its_published_sha(self):
        listing = [{"type": "file", "path": "Qwen3-4B-Q8_0.gguf", "lfs": {"oid": "b" * 64, "size": 9}},
                   {"type": "file", "path": "Qwen3-4B-Q4_K_M.gguf", "lfs": {"oid": self.SHA, "size": 2500}},
                   {"type": "file", "path": "README.md", "size": 10}]
        self.assertEqual(ai.pick_model_file(listing, "Q4_K_M"), ("Qwen3-4B-Q4_K_M.gguf", 2500, self.SHA))

    def test_model_without_sha_is_refused(self):
        with self.assertRaises(ai.LocalAIError):
            ai.pick_model_file([{"type": "file", "path": "x-Q4_K_M.gguf", "size": 5}], "Q4_K_M")

    def test_resolve_model_uses_huggingface_api(self):
        opener = FakeOpener({"https://huggingface.co/api/models/ggml-org/Qwen3-1.7B-GGUF/tree/main":
                             [{"type": "file", "path": "Qwen3-1.7B-Q4_K_M.gguf", "lfs": {"oid": self.SHA, "size": 7}}]})
        remote = ai.resolve_model("small", opener)
        self.assertEqual(remote.url, "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf")
        self.assertEqual(remote.sha256, self.SHA)

    def test_runtime_digest_must_match_the_pinned_one(self):
        name = ai.RUNTIMES["vulkan"]
        good = {"assets": [{"name": name, "size": 3, "browser_download_url": "https://github.com/x",
                            "digest": "sha256:" + ai.PINNED_SHA256[name]}]}
        self.assertEqual(ai.pick_runtime_asset(good, name).sha256, ai.PINNED_SHA256[name])
        bad = {"assets": [dict(good["assets"][0], digest="sha256:" + "c" * 64)]}
        with self.assertRaises(ai.LocalAIError):
            ai.pick_runtime_asset(bad, name)
        nodigest = {"assets": [dict(good["assets"][0], digest=None)]}
        self.assertEqual(ai.pick_runtime_asset(nodigest, name).sha256, ai.PINNED_SHA256[name])
        cpu = ai.RUNTIMES["cpu"]
        with self.assertRaises(ai.LocalAIError):
            ai.pick_runtime_asset({"assets": [{"name": cpu, "browser_download_url": "https://github.com/y"}]}, cpu)


class Download(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = b"model-bytes" * 1000
        self.sha = hashlib.sha256(self.data).hexdigest()

    def remote(self, sha=None):
        return ai.Remote("m.gguf", "https://huggingface.co/m.gguf", len(self.data), sha or self.sha)

    def test_verified_download_lands(self):
        seen = []
        dest = ai.download(self.remote(), self.tmp / "m.gguf", lambda d, t: seen.append(d),
                           opener=FakeOpener({"https://huggingface.co/m.gguf": self.data}))
        self.assertEqual(dest.read_bytes(), self.data)
        self.assertEqual(seen[-1], len(self.data))
        self.assertFalse((self.tmp / "m.gguf.part").exists())

    def test_wrong_sha_deletes_everything(self):
        with self.assertRaises(ai.LocalAIError):
            ai.download(self.remote("0" * 64), self.tmp / "m.gguf",
                        opener=FakeOpener({"https://huggingface.co/m.gguf": self.data}))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_cancel_deletes_the_partial_file(self):
        with self.assertRaises(ai.Canceled):
            ai.download(self.remote(), self.tmp / "m.gguf", cancel=lambda: True,
                        opener=FakeOpener({"https://huggingface.co/m.gguf": self.data}))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_not_enough_space_stops_before_writing(self):
        with self.assertRaises(ai.LocalAIError):
            ai.check_space(self.tmp, 5 * ai.GB, free=2 * ai.GB)

    def test_other_hosts_are_refused(self):
        with self.assertRaises(ai.LocalAIError):
            ai.download(ai.Remote("x", "https://example.com/x", 1, "a" * 64), self.tmp / "x")


class Unpack(unittest.TestCase):
    def make_zip(self, names):
        path = Path(tempfile.mkdtemp()) / "r.zip"
        with zipfile.ZipFile(path, "w") as z:
            for n in names:
                z.writestr(n, b"x")
        return path

    def test_unpacks_into_its_own_folder(self):
        base = Path(tempfile.mkdtemp())
        ai.extract_runtime(self.make_zip(["llama-server.exe", "ggml.dll"]), "cpu", base)
        self.assertEqual(ai.server_exe("cpu", base).name, "llama-server.exe")
        self.assertEqual(ai.installed_runtime(base), "cpu")

    def test_zip_slip_is_refused_and_nothing_kept(self):
        base = Path(tempfile.mkdtemp())
        with self.assertRaises(ai.LocalAIError):
            ai.extract_runtime(self.make_zip(["../evil.exe", "llama-server.exe"]), "cpu", base)
        self.assertFalse(ai.runtime_dir("cpu", base).exists())

    def test_archive_without_server_is_refused(self):
        base = Path(tempfile.mkdtemp())
        with self.assertRaises(ai.LocalAIError):
            ai.extract_runtime(self.make_zip(["readme.txt"]), "cpu", base)

    def test_remove_all_only_removes_the_ai_folder(self):
        root = Path(tempfile.mkdtemp())
        base = root / "ai"
        (base / "models").mkdir(parents=True)
        (base / "models" / "small.gguf").write_bytes(b"1234")
        (root / "keep.txt").write_text("x")
        self.assertEqual(ai.remove_all(base), 4)
        self.assertFalse(base.exists())
        self.assertTrue((root / "keep.txt").exists())


class Server(unittest.TestCase):
    def test_args_are_local_only_and_bounded(self):
        args = ai.server_args(Path("C:/ai/llama-server.exe"), Path("C:/ai/m.gguf"), 5555, "vulkan")
        self.assertIn("127.0.0.1", args)
        self.assertEqual(args[args.index("-t") + 1], str(ai.threads()))
        self.assertIn("-ngl", args)
        self.assertNotIn("-ngl", ai.server_args(Path("s"), Path("m"), 1, "cpu"))

    def test_start_chat_stop(self):
        base = Path(tempfile.mkdtemp())
        (base / "models").mkdir(parents=True)
        (base / "models" / "small.gguf").write_bytes(b"m")
        (base / "runtime" / "cpu").mkdir(parents=True)
        (base / "runtime" / "cpu" / "llama-server.exe").write_bytes(b"e")

        class Proc:
            def __init__(self, *a, **k):
                self.args, self.kwargs, self.code = a, k, None

            def poll(self):
                return self.code

            def terminate(self):
                self.code = 0

            def wait(self, timeout=None):
                return 0

        class Local:
            def open(self, request, timeout=None):
                if request.full_url.endswith("/health"):
                    return FakeResponse(b'{"status":"ok"}')
                body = json.loads(request.data)
                assert body["messages"][-1]["content"].endswith("/no_think")
                return FakeResponse(json.dumps({"choices": [{"message": {"content": "Hello"}}]}).encode())

        server = ai.LocalServer("small", base, popen=Proc, opener=Local())
        server.start("cpu", sleep=lambda s: None)
        self.assertTrue(server.running)
        self.assertEqual(server.chat([{"role": "user", "content": "hi /no_think"}]), "Hello")
        server.stop()
        self.assertFalse(server.running)

    def test_missing_files_refuse_to_start(self):
        with self.assertRaises(ai.LocalAIError):
            ai.LocalServer("small", Path(tempfile.mkdtemp())).start("cpu")


class Prompt(unittest.TestCase):
    def test_reply_rules(self):
        self.assertEqual(prompt.clean_reply("<think>hmm</think>\nYou have 4 games."), "You have 4 games.")
        self.assertEqual(prompt.clean_reply("Cyberpunk is safe to delete."), "")
        self.assertEqual(prompt.clean_reply("That freed 70 GB."), "")
        self.assertEqual(prompt.clean_reply("I deleted the cache for you."), "")
        self.assertEqual(prompt.clean_reply("  "), "")
        self.assertNotIn("\u2014", prompt.clean_reply("Big games \u2014 review them in Games."))

    def test_messages_hold_facts_lookup_and_question(self):
        f = facts()
        base = engine.answer("largest games", f)
        msgs = prompt.build_messages("what are my biggest games?", base, f, [("hi", "Hi.")])
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Starfield", msgs[0]["content"])
        self.assertIn("Never say anything is safe", msgs[0]["content"])
        self.assertEqual(msgs[-1]["content"], "what are my biggest games? /no_think")
        self.assertEqual([m["role"] for m in msgs[1:3]], ["user", "assistant"])

    def test_turned_off_sources_are_left_out(self):
        f = replace(facts(), enabled=frozenset({"history"}))
        digest = prompt.facts_digest(f)
        self.assertNotIn("Starfield", digest)
        self.assertIn("Turned off by the user", digest)


if __name__ == "__main__":
    unittest.main()
