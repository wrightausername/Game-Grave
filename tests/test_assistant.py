import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from core import ModFolder, OldFile, SteamGame
from gg_desktop import assistant_actions as actions
from gg_desktop import assistant_data as data
from gg_desktop import assistant_engine as engine
from gg_desktop.backend import Inventory
from gg_desktop.models import GameRecord

NOW = datetime(2026, 11, 8, 12, 0).astimezone()
GB = 1024 ** 3


def game(name, launcher="Steam", size=10 * GB, played_days=None, path=None):
    return GameRecord(key=f"{launcher}:{name}", name=name, launcher=launcher, app_id="1", install_path=path or f"D:\\Games\\{name}",
                      install_evidence="e", size_bytes=size, size_source="Steam manifest", last_played_at=(
                          (NOW - timedelta(days=played_days)).timestamp() if played_days is not None else None),
                      last_played_source="Steam record", status="Installed", capabilities=(), claimed_by=(launcher,))


def mod(name, path, size):
    return ModFolder(name, path, "D:\\Steam", "Mod folder", (), size, 3, False, "Steam game folder", "Review manually")


def capture(path, size):
    return SimpleNamespace(path=path, size=size, modified=1.0, device=None, inode=None, modified_ns=None)


def inventory(**extra):
    base = dict(games=[game("Cyberpunk 2077", size=70 * GB, played_days=400), game("Starfield", size=120 * GB, played_days=3),
                       game("Hades", "Epic", size=15 * GB), game("Tiny Game", size=None)],
                mods=[mod("Texture Pack", "D:\\Games\\Starfield\\Data\\tex", 2 * GB),
                      mod("Shader cache", "D:\\Steam\\shadercache\\9", 1 * GB)],
                files=[OldFile("D:\\Logs\\a.log", 5000, 1.0)], screenshots=[capture("C:\\Pics\\a.png", 2000)],
                recordings=[capture("C:\\Vids\\b.mp4", 9000)], steam=[], scanned_at="2026-11-08 10:00")
    base.update(extra)
    return Inventory(**base)


def facts(inv=None, **kw):
    return data.build_facts(inv or inventory(), (), (), now=NOW.timestamp(), **kw)


class Classify(unittest.TestCase):
    def check(self, question, intent):
        self.assertEqual(engine.classify(question, facts())[0], intent, question)

    def test_intents(self):
        self.check("What are my largest games by size?", "games")
        self.check("Where does my storage space go?", "summary")
        self.check("What is using the most space on my D: drive?", "summary")
        self.check("Explain my last cleanup", "history")
        self.check("Show my recordings and screenshots by game", "captures")
        self.check("Which games haven't I played lately?", "idle")
        self.check("what is in other storage", "other")
        self.check("any mods taking space?", "mods")
        self.check("games per launcher", "launchers")
        self.check("is it safe to delete my caches?", "safety")
        self.check("help", "help")
        self.check("", "help")
        self.check("tell me a joke", "unknown")

    def test_game_by_name(self):
        intent, found = engine.classify("Why is Cyberpunk 2077 so large?", facts())
        self.assertEqual((intent, found.name), ("profile", "Cyberpunk 2077"))

    def test_longest_name_wins(self):
        inv = inventory(games=[game("Hades"), game("Hades II")])
        self.assertEqual(engine.find_entity(facts(inv), "tell me about hades ii").name, "Hades II")

    def test_scope_sets_the_game(self):
        found = engine.find_entity(facts(scope="Epic:Hades"), "how big is it")
        self.assertEqual(found.name, "Hades")


class Answers(unittest.TestCase):
    def test_largest_games_use_reported_sizes_and_say_so(self):
        a = engine.answer("largest games", facts())
        self.assertEqual([r.label for r in a.rows][:2], ["Starfield", "Cyberpunk 2077"])
        self.assertIn("1 have no reported size", a.text)
        self.assertIn("not measured disk use", a.note)
        self.assertEqual(a.sources, ("Game library",))

    def test_summary_has_no_combined_total_and_names_its_limits(self):
        a = engine.answer("where does my storage space go", facts())
        self.assertTrue(a.rows)
        self.assertIn("don't add these rows", a.note)
        self.assertNotIn("safe", a.text.casefold())

    def test_other_storage_never_claims_safe(self):
        a = engine.answer("what is in other storage", facts())
        self.assertIn("can't tell you what is safe", a.note)
        self.assertTrue(a.handoffs)

    def test_captures_group_by_proven_owner_only(self):
        a = engine.answer("recordings by game", facts())
        self.assertIn("Owner not proven (2)", [r.label for r in a.rows])
        self.assertIn("only named when", a.note)

    def test_idle_lists_only_known_old_dates(self):
        a = engine.answer("games not played lately", facts())
        self.assertEqual(len(a.rows), 1)
        self.assertIn("Cyberpunk 2077", a.rows[0].label)
        self.assertIn("never remove", a.note)

    def test_idle_with_unknown_dates_says_so(self):
        a = engine.answer("games not played lately", facts(inventory(games=[game("A"), game("B")])))
        self.assertIn("known for 0 of 2", a.text)
        self.assertFalse(a.rows)

    def test_profile_shows_recorded_facts(self):
        a = engine.answer("why is cyberpunk 2077 so large", facts())
        labels = {r.label: r.value for r in a.rows}
        self.assertEqual(labels["Launcher"], "Steam")
        self.assertEqual(labels["Reported size"], "70.0 GB")
        self.assertIn("Game DNA", [h[1] for h in a.handoffs])

    def test_mod_use_is_not_invented(self):
        a = engine.answer("which mods have no recent use", facts())
        self.assertIn("doesn't track when a mod was last used", a.text)
        self.assertFalse(a.rows)

    def test_mods_scoped_to_a_game(self):
        a = engine.answer("mods for Starfield", facts())
        self.assertEqual([r.label for r in a.rows], ["Texture Pack"])

    def test_safety_never_says_safe_and_points_to_tabs(self):
        a = engine.answer("is it safe to delete this", facts())
        self.assertIn("can't tell you that something is safe", a.text)
        self.assertIn("Graveyard", [h[1] for h in a.handoffs])

    def test_history(self):
        records = [{"id": "r1", "path": "D:\\Games\\Hades\\x.bin", "size": 100, "time": (NOW - timedelta(days=1)).isoformat(),
                    "action": "Old Files", "state": "Available", "note": "n"}]
        f = data.build_facts(inventory(), records, [], now=NOW.timestamp())
        a = engine.answer("explain my last cleanup", f)
        self.assertIn("1 recycled", a.text)
        self.assertIn("Undo Center", [h[1] for h in a.handoffs])
        self.assertIn("isn't a promise", a.note)

    def test_launchers(self):
        a = engine.answer("games per launcher", facts())
        self.assertEqual([r.label for r in a.rows], ["Steam (3)", "Epic (1)"])


class Sources(unittest.TestCase):
    def test_disabled_source_is_named_not_guessed(self):
        a = engine.answer("largest games", facts(enabled={"storage"}))
        self.assertEqual(a.intent, "off")
        self.assertIn("Game library is turned off", a.text)
        self.assertFalse(a.rows)

    def test_nothing_scanned_points_to_scan(self):
        a = engine.answer("largest games", facts(inventory(games=[], mods=[], files=[], screenshots=[], recordings=[], scanned_at="")))
        self.assertEqual(a.intent, "empty")
        self.assertIn("Run Scan PC", a.text)

    def test_summary_notes_what_is_off(self):
        a = engine.answer("where does my space go", facts(enabled={"library", "storage"}))
        self.assertIn("Turned off: Mods inventory, Captures index", a.note)

    def test_source_states_and_metrics(self):
        f = facts(enabled={"library", "history"})
        states = {s.key: s for s in data.source_states(f)}
        self.assertTrue(states["library"].enabled)
        self.assertFalse(states["captures"].enabled)
        m = data.metrics(f, 3)
        self.assertEqual((m["conversations"], m["games"], m["sources_on"], m["sources_total"]), (3, 4, 2, 5))
        self.assertEqual(m["scan"], "2h ago")

    def test_enabled_sources_setting_is_validated(self):
        self.assertEqual(data.enabled_sources({}), frozenset(data.DEFAULT_ENABLED))
        self.assertEqual(data.enabled_sources({"assistant_sources": ["library", "bogus"]}), frozenset({"library"}))
        self.assertEqual(data.enabled_sources({"assistant_sources": "x"}), frozenset(data.DEFAULT_ENABLED))
        self.assertEqual(data.with_sources({}, {"mods", "library"})["assistant_sources"], ["library", "mods"])

    def test_when_text(self):
        now = NOW.timestamp()
        self.assertEqual(data.when_text("2026-11-08 11:59", now), "Just now")
        self.assertEqual(data.when_text("2026-11-05 12:00", now), "3d ago")
        self.assertEqual(data.when_text("nonsense", now), "Not scanned")


class Chats(unittest.TestCase):
    def test_exchange_round_trip(self):
        chat = actions.new_chat(1000)
        a = engine.answer("largest games", facts())
        actions.add_exchange(chat, "  What are my   largest games?  ", a, 1001)
        self.assertEqual(chat["title"], "What are my largest games?")
        settings = actions.with_chats({"x": 1}, [chat])
        self.assertEqual(settings["x"], 1)
        loaded = actions.load_chats(settings)
        self.assertEqual(len(loaded[0]["messages"]), 2)
        self.assertEqual(engine.answer_from_dict(loaded[0]["messages"][1]["answer"]).rows, a.rows)

    def test_damaged_settings_never_break_loading(self):
        for bad in (None, "x", [1, None, {"id": 3}], [{"id": "a", "messages": [{"role": "assistant", "text": "t", "answer": {"x": 1}}]}]):
            self.assertIsInstance(actions.load_chats({"assistant_chats": bad}), list)

    def test_limits(self):
        chats = []
        for i in range(30):
            c = actions.new_chat(1000 + i)
            for j in range(30):
                actions.add_exchange(c, "q" * 400, engine.answer("largest games", facts()), 1000 + i)
            chats.append(c)
        saved = actions.with_chats({}, chats)["assistant_chats"]
        self.assertLessEqual(len(saved), actions.MAX_CHATS)
        import json
        self.assertLessEqual(len(json.dumps(saved)), actions.MAX_BYTES)
        c = actions.add_exchange(actions.new_chat(1), "q", engine.answer("help", facts()), 2)
        for _ in range(60):
            actions.add_exchange(c, "q", engine.answer("help", facts()), 3)
        self.assertLessEqual(len(c["messages"]), actions.MAX_MESSAGES)

    def test_clear_and_delete(self):
        c = actions.add_exchange(actions.new_chat(1), "hi", engine.answer("help", facts()), 2)
        actions.clear_chat(c)
        self.assertEqual((c["messages"], c["title"]), ([], actions.NEW_TITLE))
        self.assertEqual(actions.delete_chat([c], c["id"]), [])

    def test_scope_setting(self):
        self.assertEqual(actions.scope_of({"assistant_scope": "k"}), "k")
        self.assertEqual(actions.scope_of({"assistant_scope": 5}), "")
        self.assertEqual(actions.with_scope({}, None)["assistant_scope"], "")

    def test_copy_text(self):
        a = engine.answer("largest games", facts())
        text = actions.answer_text("largest games", a)
        self.assertTrue(text.startswith("Q: largest games"))
        self.assertIn("Sources: Game library", text)

    def test_no_answer_ever_says_safe_to_remove(self):
        for q in ("largest games", "other storage", "recordings", "mods", "where does space go", "unused games",
                  "explain my last cleanup", "launchers", "cyberpunk", "tell me a joke"):
            a = engine.answer(q, facts())
            blob = (a.text + " " + a.note).casefold()
            for phrase in ("safe to remove", "safe to delete", "safe to clear", "freed", "reclaimed"):
                self.assertNotIn(phrase, blob.replace("can't tell you what is safe to clear", ""), (q, phrase))


if __name__ == "__main__":
    unittest.main()


class FeatureQuestions(unittest.TestCase):
    def test_resurrection_kit_help_is_answered(self):
        for q in ("help me with the resurrection kit", "what is the Resurrection Kit?", "how do I use ressurection kits",
                  "what does a kit do"):
            a = engine.answer(q, facts())
            self.assertEqual(a.intent, "feature", q)
            self.assertIn("ZIP", a.text)
            self.assertIn("More Tools", a.text)
            self.assertNotIn("I answer from what Game Grave has already scanned", a.text)
            self.assertEqual(a.handoffs, (("Open More Tools", "More Tools"),))

    def test_other_features(self):
        for q, title in (("how does save vault work", "Save Vault"), ("what does black box do", "Black Box"),
                         ("explain soulbind", "Soulbind"), ("what is exhume", "Exhume"),
                         ("what is game dna", "Game DNA"), ("what does the undo center do", "Undo Center")):
            a = engine.answer(q, facts())
            self.assertEqual(a.intent, "feature", q)
            self.assertTrue(a.text.startswith(title), a.text[:40])

    def test_scan_questions_still_use_scan_data(self):
        self.assertEqual(engine.classify("any mods taking space?", facts())[0], "mods")
        self.assertEqual(engine.classify("Explain my last cleanup", facts())[0], "history")
        self.assertEqual(engine.classify("help", facts())[0], "help")
        self.assertEqual(engine.classify("tell me a joke", facts())[0], "unknown")

    def test_no_safe_claims_and_safety_note(self):
        a = engine.answer("is it safe to delete old files", facts())
        self.assertEqual(a.intent, "feature")
        self.assertIn("can't tell you that something is safe", a.note)
        for f in __import__("gg_desktop.assistant_features", fromlist=["x"]).FEATURES:
            blob = (f.what + " ".join(f.steps) + f.never + f.hover).casefold()
            self.assertNotIn("is safe", blob, f.key)
            self.assertNotIn("safe to remove", blob, f.key)

    def test_hover_text_is_specific(self):
        from gg_desktop import tools_data
        for key, title, hint in tools_data.KIT_ACTIONS:
            self.assertGreater(len(hint.split()), 12, key)
        self.assertIn("verified ZIP", tools_data.tile("resurrection_kit").note)

    def test_a_game_named_like_a_feature_is_still_a_game_question(self):
        inv = inventory(games=[game("Graveyard Keeper", size=2 * GB), game("Hades")])
        f = facts(inv)
        self.assertEqual(engine.answer("how big is Graveyard Keeper?", f).intent, "profile")
        self.assertEqual(engine.answer("what is the graveyard?", f).intent, "feature")
        self.assertEqual(engine.answer("make a resurrection kit for Graveyard Keeper", f).intent, "feature")

    def test_newer_features_are_explained(self):
        for q, title in (("how does mod bisect work", "Mod Bisect"), ("which mod is crashing my game", "Mod Bisect"),
                         ("what does the hardware tab do", "Hardware"), ("how do I update game grave", "Check for Updates")):
            a = engine.answer(q, facts())
            self.assertEqual(a.intent, "feature", q)
            self.assertTrue(a.text.startswith(title), (q, a.text[:40]))
        self.assertEqual(engine.classify("any mods taking space?", facts())[0], "mods")
