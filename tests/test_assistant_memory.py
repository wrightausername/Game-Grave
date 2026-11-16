"""Undo by asking, fix history, notes and scan news. Pure."""
import unittest

from gg_desktop import assistant_memory as m


def chat_with(steps):
    return {"messages": [{"role": "user", "text": "get my pc ready"},
                         {"role": "assistant", "text": "plan", "plan": {"request": "get my pc ready", "steps": steps}}]}


class Undo(unittest.TestCase):
    def test_words(self):
        for t in ("undo that", "Undo.", "put it back", "revert that", "undo what you just did", "take that back"):
            self.assertTrue(m.is_undo(t), t)
        for t in ("how do i undo a cleanup", "undo center", "what can i undo"):
            self.assertFalse(m.is_undo(t), t)

    def test_reverses_only_finished_changes_through_existing_paths(self):
        steps, notes, request = m.undo_steps(chat_with([
            {"key": "game_mode_on", "args": {}, "status": "done"},
            {"key": "recording_off", "args": {}, "status": "done"},
            {"key": "mod_off", "args": {"name": "SkyUI", "folder": "C:\\p"}, "status": "done"},
            {"key": "startup_off", "args": {"name": "Spotify", "key": "k"}, "status": "done"},
            {"key": "clear_temp", "args": {}, "status": "done"},
            {"key": "power_high", "args": {}, "status": "skipped"},
            {"key": "check_temp", "args": {}, "status": "done"}]))
        self.assertEqual([s.key for s in steps], ["undo_optimizer", "mod_on", "startup_on"])
        self.assertEqual(steps[1].args["name"], "SkyUI")
        self.assertTrue(any("can't be brought back" in n for n in notes))
        self.assertEqual(request, "get my pc ready")

    def test_nothing_to_undo(self):
        self.assertEqual(m.undo_steps({"messages": []})[0], None)
        self.assertEqual(m.undo_steps(chat_with([{"key": "check_temp", "status": "done"}]))[0], None)


class FixHistory(unittest.TestCase):
    def test_record_answer_and_line(self):
        s = m.record_fix({}, "Hades", "Ask Steam to check Hades's files")
        s = m.mark_last(s, "Hades", "not_fixed")
        self.assertEqual(m.tried_for(s, "Hades")[0]["result"], "not_fixed")
        self.assertIn("didn't help", m.tried_line(s, "Hades"))
        self.assertEqual(m.tried_line(s, "Starfield"), "")

    def test_replies(self):
        self.assertEqual(m.fix_reply("it's fixed"), "fixed")
        self.assertEqual(m.fix_reply("Yes, it's fixed!"), "fixed")
        self.assertEqual(m.fix_reply("still broken"), "not_fixed")
        self.assertEqual(m.fix_reply("no, it didn't help"), "not_fixed")
        self.assertEqual(m.fix_reply("how big is starfield"), "")


class Notes(unittest.TestCase):
    def test_remember_recall_forget(self):
        self.assertEqual(m.note_command("Remember that I mod Skyrim with Vortex."), ("remember", "I mod Skyrim with Vortex"))
        self.assertEqual(m.note_command("what do you remember about me")[0], "recall")
        self.assertEqual(m.note_command("how big is starfield"), ("", ""))
        s = m.add_note({}, "I mod Skyrim with Vortex")
        s = m.add_note(s, "Don't suggest uninstalling Elden Ring")
        self.assertIn("Elden Ring", m.notes_text(s))
        s2, gone = m.forget(s, "elden ring")
        self.assertEqual(gone, ["Don't suggest uninstalling Elden Ring"])
        s3, gone = m.forget(s, "note 1")
        self.assertEqual(gone, ["I mod Skyrim with Vortex"])
        s4, gone = m.forget(s, "all notes")
        self.assertEqual((m.notes(s4), len(gone)), ([], 2))
        self.assertEqual(m.note_command("forget note 2"), ("forget", "2"))
        self.assertEqual(m.note_command("forget it"), ("", ""), "plain \"forget it\" is not a note command")


class News(unittest.TestCase):
    def test_only_what_changed(self):
        self.assertEqual(m.scan_news(["A", "B"], ["A", "B"]), [])
        lines = m.scan_news(["A", "B"], ["A", "C"], ["D:"], 3, 5)
        self.assertEqual(lines[0], "Drive D: is almost full.")
        self.assertTrue(any("New since the last scan: C" in x for x in lines))
        self.assertEqual(len(lines), 3)
        self.assertEqual(m.scan_news([], ["A"]), [], "the first scan has nothing to compare with")


if __name__ == "__main__":
    unittest.main()
