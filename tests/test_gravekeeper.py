import json
import unittest

from gg_desktop import gravekeeper as gk
from tests.test_local_ai_tools import ctx


def call(fn, **args):
    return {"content": "", "tool_calls": [{"id": "c1", "type": "function",
                                           "function": {"name": fn, "arguments": json.dumps(args)}}]}


class Script:
    """A stand-in model: replies in order, records what it was sent."""

    def __init__(self, *replies, plain=""):
        self.replies = list(replies)
        self.sent = []
        self.plain = plain

    def chat_message(self, msgs, tools, **k):
        self.sent.append((msgs, tools, k))
        return self.replies.pop(0) if self.replies else {"content": "Done looking."}

    def chat(self, msgs, **k):
        self.sent.append((msgs, None, k))
        return self.plain


class Persona(unittest.TestCase):
    def test_system_text_has_persona_memory_and_lessons(self):
        c = ctx(memory="- Earlier chat \"Skyrim\": they asked \"why does skyrim crash\"", waiting_plan="Clean temp files")
        msgs = gk.messages("hey", c.facts, [("hi", "Hey there.")], c, notes="1. I stream on Twitch",
                           lessons="- Asked x, you said y", memory=c.memory)
        system = msgs[0]["content"]
        self.assertIn("You are the Gravekeeper", system)
        self.assertIn("why does skyrim crash", system)
        self.assertIn("I stream on Twitch", system)
        self.assertIn("Mistakes you made before", system)
        self.assertIn("A plan is waiting", system)
        self.assertNotIn("—", system)
        self.assertEqual([m["role"] for m in msgs[1:]], ["user", "assistant", "user"])

    def test_screenshot_goes_with_the_question(self):
        c = ctx()
        msgs = gk.messages("what is this?", c.facts, [], c, image="data:image/png;base64,AAAA")
        parts = msgs[-1]["content"]
        self.assertEqual(parts[1]["image_url"]["url"], "data:image/png;base64,AAAA")

    def test_lessons(self):
        s = gk.add_lesson({}, "how big is cyberpunk", "It's 999 GB.", "no, it's 70 GB")
        self.assertIn("no, it's 70 GB", gk.lessons_text(s))
        for i in range(30):
            s = gk.add_lesson(s, f"q{i}", "a")
        self.assertEqual(len(s[gk.LESSONS_KEY]), gk.MAX_LESSONS)
        self.assertTrue(gk.CORRECTION.search("No, that's wrong"))
        self.assertFalse(gk.CORRECTION.search("Nothing else, thanks"))

    def test_memory_text(self):
        chats = [{"id": "a", "title": "Space", "updated": 2, "messages": [{"role": "user", "text": "where did my space go"}]},
                 {"id": "b", "title": "Now", "updated": 3, "messages": [{"role": "user", "text": "hello"}]}]
        text = gk.memory_text(chats, "b", {"Starfield": [{"tried": "Verify", "result": "not_fixed"}]})
        self.assertIn("where did my space go", text)
        self.assertNotIn("hello", text)
        self.assertIn("Starfield: tried Verify (not_fixed)", text)


class Tools(unittest.TestCase):
    def test_effects_are_recorded_not_applied(self):
        c = ctx(effects=[], undo_preview="Undo: get my PC ready", waiting_plan="Clean temp files")
        gk.run(c, "remember", {"note": "I play on a laptop"})
        gk.run(c, "offer_button", {"label": "Open Fix Kit", "opens": "Fix Kit"})
        gk.run(c, "offer_button", {"label": "x", "opens": "Toolbox"})
        gk.run(c, "show_chart", {"kind": "space"})
        gk.run(c, "show_game", {"name": "cyberpunk"})
        gk.run(c, "undo_last", {})
        gk.run(c, "run_waiting_plan", {})
        self.assertIn(("note_add", "I play on a laptop"), c.effects)
        self.assertIn(("button", "Open Fix Kit", "Fix Kit"), c.effects)
        self.assertIn(("button", "x", "More Tools"), c.effects)          # Toolbox is the More Tools route
        self.assertIn(("chart", "space"), c.effects)
        self.assertIn(("game_card", "Cyberpunk 2077"), c.effects)
        self.assertIn(("undo",), c.effects)
        self.assertIn(("run_plan",), c.effects)

    def test_refusals(self):
        c = ctx(effects=[])
        self.assertIn("error", json.loads(gk.run(c, "offer_button", {"label": "x", "opens": "Format Drive"})))
        self.assertIn("error", json.loads(gk.run(c, "show_game", {"name": "Half-Life 3"})))
        self.assertIn("note", json.loads(gk.run(c, "undo_last", {})))
        self.assertIn("note", json.loads(gk.run(c, "run_waiting_plan", {})))
        self.assertEqual(c.effects, [])

    def test_wiki_link_is_a_button_not_copied_text(self):
        c = ctx(effects=[])
        out = json.loads(gk.run(c, "game_page", {"name": "cyberpunk"}))
        self.assertIn("button_shown", out)
        kind, label, url = c.effects[0]
        self.assertEqual(kind, "link")
        self.assertTrue(url.startswith("https://pcgamingwiki.com/api/appid.php?appid=") or "pcgamingwiki.com" in url)

    def test_what_to_play_lists_the_library(self):
        c = ctx(modes={})
        out = json.loads(gk.run(c, "what_to_play", {"mood": "something chill"}))
        self.assertEqual(out["count"], len(c.facts.games))

    def test_past_chats(self):
        c = ctx(all_chats=[{"id": "x", "title": "Crash", "messages": [{"role": "user", "text": "skyrim crashes on load"}]}],
                chat_id="now")
        out = json.loads(gk.run(c, "past_chats", {"query": "skyrim crashes"}))
        self.assertEqual(out["matches"][0]["chat"], "Crash")

    def test_specs_have_every_tool(self):
        names = {s["function"]["name"] for s in gk.agent_specs()}
        self.assertTrue({"make_plan", "look_up_game", "remember", "offer_button", "show_chart", "what_to_play",
                         "game_page", "run_waiting_plan", "undo_last"} <= names)
        for s in gk.agent_specs():
            props = s["function"]["parameters"]["properties"]
            self.assertFalse(any("optional" in v for v in props.values()), s["function"]["name"])


class Turn(unittest.TestCase):
    def test_looks_up_narrates_then_answers(self):
        said = []
        server = Script({"content": "Let me look at it.", "tool_calls": call("look_up_game", name="Cyberpunk 2077")
                         ["tool_calls"]}, {"content": "Cyberpunk 2077 reports 70.0 GB on drive C:."})
        out = gk.turn(server, "tell me about cyberpunk", ctx().facts, [], ctx(), events=lambda k, t: said.append((k, t)))
        self.assertEqual(out["text"], "Cyberpunk 2077 reports 70.0 GB on drive C:.")
        self.assertIn(("say", "Let me look at it."), said)
        self.assertIn("look_up_game", out["looked"])
        self.assertIn("think", server.sent[0][2])

    def test_a_plan_from_a_request(self):
        server = Script(call("make_plan", summary="Clear old temp files.", jobs=[{"job": "clean_temp_files"}]),
                        {"content": "I'll clear the old temp files once you press Run all."})
        out = gk.turn(server, "clean up my temp files please", ctx().facts, [], ctx())
        self.assertEqual(out["jobs"], [{"job": "clean_temp_files"}])
        self.assertIn("Run all", out["text"])

    def test_a_question_never_becomes_a_plan(self):
        server = Script(call("make_plan", summary="x", jobs=[{"job": "clean_temp_files"}]),
                        {"content": "Temp files are leftovers apps make; Windows Cleanup can clear old ones."})
        out = gk.turn(server, "what are temp files?", ctx().facts, [], ctx())
        self.assertIsNone(out["jobs"])

    def test_rules_still_checked_in_code(self):
        server = Script({"content": "Cyberpunk is safe to delete."}, plain="Cyberpunk reports 70.0 GB. Review it in Games.")
        out = gk.turn(server, "can i delete cyberpunk", ctx().facts, [], ctx())
        self.assertNotIn("safe to delete", out["text"])
        self.assertIn("Review it in Games", out["text"])

    def test_wrong_size_corrected(self):
        server = Script({"content": "Cyberpunk 2077 takes 333 GB."}, plain="Cyberpunk 2077 reports 70.0 GB.")
        out = gk.turn(server, "how big is cyberpunk", ctx().facts, [], ctx())
        self.assertEqual(out["text"], "Cyberpunk 2077 reports 70.0 GB.")

    def test_effects_come_back(self):
        server = Script(call("remember", note="I have a 4090"), {"content": "Got it, I'll remember that."})
        out = gk.turn(server, "remember that I have a 4090", ctx().facts, [], ctx())
        self.assertIn(("note_add", "I have a 4090"), out["effects"])


if __name__ == "__main__":
    unittest.main()


class Asked(unittest.TestCase):
    def test_questions_and_requests(self):
        self.assertTrue(gk.asked_not_told("what are temp files?"))
        self.assertTrue(gk.asked_not_told("how do I find which mod is crashing my game"))
        self.assertFalse(gk.asked_not_told("my pc feels full of junk, sort it out"))
        self.assertFalse(gk.asked_not_told("clean up my temp files please"))
