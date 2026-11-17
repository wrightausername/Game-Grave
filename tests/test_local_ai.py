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
        self.assertEqual([m.key for m in ai.MODELS], ["small", "medium", "large", "xl"])
        self.assertLessEqual(max(m.approx_bytes for m in ai.MODELS), ai.MAX_DOWNLOAD)
        for m in ai.MODELS:
            self.assertTrue(m.repo.startswith("unsloth/Qwen3.5-"), m.repo)     # Qwen 3.5, Apache 2.0, GGUF by Unsloth


class Resolve(unittest.TestCase):
    SHA = "a" * 64

    def test_model_file_and_its_published_sha(self):
        listing = [{"type": "file", "path": "Qwen3-4B-Q8_0.gguf", "lfs": {"oid": "b" * 64, "size": 9}},
                   {"type": "file", "path": "Qwen3-4B-Q4_K_M.gguf", "lfs": {"oid": self.SHA, "size": 2500}},
                   {"type": "file", "path": "README.md", "size": 10}]
        self.assertEqual(ai.pick_model_file(listing, "Q4_K_M"), ("Qwen3-4B-Q4_K_M.gguf", 2500, self.SHA))

    def test_plain_name_wins_over_variants(self):
        listing = [{"type": "file", "path": "Qwen3-8B-UD-Q4_K_M.gguf", "lfs": {"oid": "b" * 64, "size": 9}},
                   {"type": "file", "path": "Qwen3-8B-Q4_K_M.gguf", "lfs": {"oid": self.SHA, "size": 5}},
                   {"type": "file", "path": "Qwen3-8B-Q4_K_M-00001-of-00002.gguf", "lfs": {"oid": "c" * 64, "size": 1}}]
        self.assertEqual(ai.pick_model_file(listing, "Q4_K_M")[0], "Qwen3-8B-Q4_K_M.gguf")

    def test_missing_quant_names_what_is_there(self):
        with self.assertRaises(ai.LocalAIError) as caught:
            ai.pick_model_file([{"type": "file", "path": "Qwen3-8B-Q8_0.gguf", "lfs": {"oid": self.SHA}}], "Q4_K_M")
        self.assertIn("Qwen3-8B-Q8_0.gguf", str(caught.exception))

    def test_model_without_sha_is_refused(self):
        with self.assertRaises(ai.LocalAIError):
            ai.pick_model_file([{"type": "file", "path": "x-Q4_K_M.gguf", "size": 5}], "Q4_K_M")

    def test_resolve_model_uses_huggingface_api(self):
        listing = [{"type": "file", "path": "Qwen3.5-2B-Q4_K_M.gguf", "lfs": {"oid": self.SHA, "size": 7}},
                   {"type": "file", "path": "mmproj-BF16.gguf", "lfs": {"oid": "d" * 64, "size": 3}},
                   {"type": "file", "path": "mmproj-F16.gguf", "lfs": {"oid": "e" * 64, "size": 3}}]
        opener = FakeOpener({"https://huggingface.co/api/models/unsloth/Qwen3.5-2B-GGUF/tree/main": listing})
        remote = ai.resolve_model("small", opener)
        self.assertEqual(remote.url, "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf")
        self.assertEqual(remote.sha256, self.SHA)
        vision = ai.resolve_vision("small", opener)          # the F16 image file is preferred
        self.assertEqual((vision.name, vision.sha256), ("mmproj-F16.gguf", "e" * 64))
        self.assertIsNone(ai.pick_vision_file(listing[:1]))

    def test_runtime_digest_is_githubs(self):
        name = ai.RUNTIMES["vulkan"]
        good = {"assets": [{"name": name, "size": 3, "browser_download_url": "https://github.com/x",
                            "digest": "sha256:" + "b" * 64}]}
        self.assertEqual(ai.pick_runtime_asset(good, name).sha256, "b" * 64)
        nodigest = {"assets": [dict(good["assets"][0], digest=None)]}
        with self.assertRaises(ai.LocalAIError):              # no fingerprint, no download
            ai.pick_runtime_asset(nodigest, name)
        pinned = dict(ai.PINNED_SHA256)
        try:
            ai.PINNED_SHA256[name] = "a" * 64                  # a pinned value that disagrees with GitHub is refused
            with self.assertRaises(ai.LocalAIError):
                ai.pick_runtime_asset(good, name)
        finally:
            ai.PINNED_SHA256.clear()
            ai.PINNED_SHA256.update(pinned)
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
        (base / "models" / "small-q35.gguf").write_bytes(b"m")
        (base / "models" / "small-q35-mmproj.gguf").write_bytes(b"v")
        (base / "runtime" / ai.RUNTIME_TAG / "cpu").mkdir(parents=True)
        (base / "runtime" / ai.RUNTIME_TAG / "cpu" / "llama-server.exe").write_bytes(b"e")

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
                assert body["chat_template_kwargs"] == {"enable_thinking": False}
                return FakeResponse(json.dumps({"choices": [{"message": {"content": "Hello"}}]}).encode())

        server = ai.LocalServer("small", base, popen=Proc, opener=Local())
        server.start("cpu", sleep=lambda s: None)
        self.assertTrue(server.running)
        self.assertTrue(server.vision)                        # the image file is passed with --mmproj
        self.assertIn("--mmproj", server.process.args[0])
        self.assertEqual(server.chat([{"role": "user", "content": "hi"}], think=False), "Hello")
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
        # Only real promises are blocked; ordinary uses of "safe" and "free" get through.
        self.assertTrue(prompt.clean_reply("Your saves are safe: Game Grave never offers them for removal."))
        self.assertTrue(prompt.clean_reply("You could free up space by reviewing Other Storage."))
        self.assertEqual(prompt.clean_reply("Recycling these freed up about 12 GB."), "")
        self.assertEqual(prompt.clean_reply("Your Windows settings have been restored."), "", "it never reports a change as done")
        self.assertEqual(prompt.clean_reply("None"), "", "a bare None is no answer")
        self.assertEqual(prompt.clean_reply("<think>still working it out"), "", "unfinished thinking never shows")
        self.assertEqual(prompt.clean_reply("**Starfield** is your biggest game."), "Starfield is your biggest game.")

    def test_messages_hold_facts_lookup_and_question(self):
        f = facts()
        base = engine.answer("largest games", f)
        msgs = prompt.build_messages("what are my biggest games?", base, f, [("hi", "Hi.")])
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Starfield", msgs[0]["content"])
        self.assertIn("Never promise that something is safe", msgs[0]["content"])
        self.assertTrue(msgs[-1]["content"].endswith("what are my biggest games? /no_think"))
        self.assertIn("quick lookup", msgs[-1]["content"], "the lookup goes with the question, not the cached system text")
        other = prompt.build_messages("how many mods", engine.answer("how many mods", f), f)
        self.assertEqual(other[0]["content"], msgs[0]["content"], "the system text is the same for every question")
        self.assertEqual([m["role"] for m in msgs[1:3]], ["user", "assistant"])

    def test_model_knows_what_game_grave_already_does(self):
        f = facts()
        msgs = prompt.build_messages("what features should game grave add?", engine.answer("help", f), f)
        system = msgs[0]["content"]
        for name in ("Autopsy (Fix Kit)", "Mod Bisect (Mods)", "Resurrection Kit (Fix Kit)", "Drivers & Startup"):
            self.assertIn(name, system)
        self.assertIn("Never say a feature is missing", system)
        self.assertLess(len(system), prompt.CONTEXT_CHARS + 12000, "the prompt stays well inside the model's context")

    def test_a_keyword_miss_is_not_handed_to_the_model(self):
        f = facts()
        miss = engine.answer("zzqq blorp", f)
        self.assertEqual(miss.intent, "unknown")
        sent = " ".join(m["content"] for m in prompt.build_messages("zzqq blorp", miss, f))
        self.assertNotIn("I don't have an answer", sent)
        self.assertNotIn("quick lookup", sent)
        found = prompt.build_messages("biggest games", engine.answer("largest games", f), f)[-1]["content"]
        self.assertIn("quick lookup", found)

    def test_thinking_models_reason_and_keep_more_history(self):
        f = facts()
        pairs = [(f"q{i}", f"a{i}") for i in range(10)]
        msgs = prompt.build_messages("why?", engine.answer("help", f), f, pairs, think=True)
        self.assertEqual(msgs[-1]["content"], "why?", "no /no_think when the model may think")
        self.assertEqual(len(msgs), 1 + 12 + 1, "the last six exchanges are kept")
        self.assertIn("medium", ai.THINKS)
        self.assertNotIn("small", ai.THINKS)

    def test_a_plain_request_can_become_a_known_plan_only(self):
        self.assertEqual(prompt.plan_request("PLAN: clean up temp files"), "clean up temp files")
        self.assertEqual(prompt.plan_request("plan: Fix my game."), "fix my game")
        self.assertEqual(prompt.plan_request("PLAN: format my drive"), "", "only jobs Game Grave knows")
        self.assertEqual(prompt.plan_request("Your biggest game is Starfield."), "")
        self.assertIn("PLAN:", prompt.build_messages("tidy my pc", None, facts())[0]["content"])

    def test_digest_links_saves_mods_and_captures_to_their_game(self):
        f = facts()
        digest = prompt.facts_digest(f)
        self.assertIn("GAMES:", digest)
        self.assertLessEqual(len(digest), prompt.CONTEXT_CHARS + 60)

    def test_turned_off_sources_are_left_out(self):
        f = replace(facts(), enabled=frozenset({"history"}))
        digest = prompt.facts_digest(f)
        self.assertNotIn("Starfield", digest)
        self.assertIn("Turned off by the user", digest)


if __name__ == "__main__":
    unittest.main()


class Recommend(unittest.TestCase):
    def test_sizes_follow_memory_and_graphics_memory(self):
        self.assertEqual(ai.recommend(8, 0), "small")
        self.assertEqual(ai.recommend(16, 0), "medium")
        self.assertEqual(ai.recommend(16, 8), "large")
        self.assertEqual(ai.recommend(32, 12), "xl")
        self.assertEqual(ai.recommend(32, 6), "xl", "the 35B mixture of experts lives mostly in memory")
        self.assertEqual(ai.recommend(32, 4), "medium")
        self.assertEqual(ai.recommend(16, 12), "large", "Extra Large needs 32 GB of memory too")
        self.assertEqual(ai.recommend(0, 0), "small")


class Generations(unittest.TestCase):
    def test_older_qwen3_file_still_runs_and_asks_for_update(self):
        base = Path(tempfile.mkdtemp())
        (base / "models").mkdir(parents=True)
        (base / "models" / "large.gguf").write_bytes(b"old")
        self.assertEqual(ai.installed_models(base), ["large"])
        self.assertTrue(ai.is_legacy("large", base))
        self.assertEqual(ai.model_file("large", base).name, "large.gguf")
        self.assertFalse(ai.sees_images("large", base))
        (base / "models" / "large-q35.gguf").write_bytes(b"new")
        self.assertFalse(ai.is_legacy("large", base))
        self.assertEqual(ai.remove_model("large", base), 6)
        self.assertEqual(ai.installed_models(base), [])

    def test_engine_folder_is_per_version(self):
        base = Path(tempfile.mkdtemp())
        (base / "runtime" / "vulkan").mkdir(parents=True)       # an older engine folder
        (base / "runtime" / "vulkan" / "llama-server.exe").write_bytes(b"e")
        self.assertEqual(ai.installed_runtime(base), "")         # not the version Qwen 3.5 needs
        self.assertEqual([p.name for p in ai.old_runtimes(base)], ["vulkan"])

    def test_big_model_keeps_experts_in_memory(self):
        args = ai.server_args("s.exe", "m.gguf", 1, "vulkan", 4096, None, moe=True)
        self.assertIn("--cpu-moe", args)
        self.assertNotIn("--cpu-moe", ai.server_args("s.exe", "m.gguf", 1, "cpu", 4096, None, moe=True))
