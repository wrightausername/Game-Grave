import unittest

from gg_desktop import mods_gallery_data as gd
from gg_desktop.mods_gallery_data import Facts


def facts(name="Mod", index=0, game="Skyrim", **kw):
    return Facts(index, "/m/" + name, name, game, kw.pop("manager", "Vortex"), **kw)


class StatusTests(unittest.TestCase):
    def test_conflict_outranks_update_outranks_saved_state(self):
        both = facts(word="On", outdated=True, newest="2", conflicts=1)
        self.assertEqual(gd.status_of(both), ("Conflict", "red"))
        self.assertEqual(gd.status_of(facts(word="On", outdated=True)), ("Update ready", "amber"))
        self.assertEqual(gd.status_of(facts(word="On")), ("On", "green"))
        self.assertEqual(gd.status_of(facts(word="Off")), ("Off", "muted"))
        self.assertEqual(gd.status_of(facts(word="On in some")), ("On in some", "amber"))
        self.assertEqual(gd.status_of(facts(word="Storage folder")), ("Storage folder", "muted"))

    def test_unchecked_means_no_flag(self):
        """None means the check has not run. It must never turn into a conflict or an update."""
        card = gd.card(facts(word="On", outdated=None, conflicts=None))
        self.assertEqual((card.label, card.action), ("On", ""))

    def test_notes_say_what_is_known_and_nothing_more(self):
        self.assertEqual(gd.note_for(facts(conflicts=1, partners=("Beta",))), "Shares files with Beta")
        self.assertEqual(gd.note_for(facts(conflicts=2, partners=("A", "B"))), "Shares files with A and B")
        self.assertEqual(gd.note_for(facts(conflicts=3, partners=("A", "B", "C", "D"))), "Shares files with A, B and 2 more")
        self.assertEqual(gd.note_for(facts(conflicts=1)), "Shares files with another mod")
        self.assertIn("1.3", gd.note_for(facts(outdated=True, newest="1.3")))
        self.assertIn("newer version", gd.note_for(facts(outdated=True, newest="Unknown")))
        self.assertEqual(gd.note_for(facts(word="Not recorded")), "Your mod manager has not saved whether it is on")

    def test_no_card_claims_anything_is_safe_or_offers_to_fix(self):
        every = [facts(word=w, outdated=o, conflicts=c, partners=("X",), newest="2")
                 for w in gd.STATUS_WORDS for o in (None, False, True) for c in (None, 0, 2)]
        for f in every:
            card = gd.card(f)
            text = " ".join((card.label, card.note, card.action, card.version_text)).casefold()
            self.assertNotIn("safe", text)
            self.assertNotIn("remove", text)
            self.assertIn(card.action, ("", "Review", "Details"), "Game Grave never installs or changes a mod")
            self.assertIn(card.tone, gd.TONES)

    def test_actions(self):
        self.assertEqual(gd.action_for(facts(conflicts=1)), "Review")
        self.assertEqual(gd.action_for(facts(outdated=True)), "Details")
        self.assertEqual(gd.action_for(facts(word="On")), "")

    def test_version_text(self):
        self.assertEqual(gd.version_text(facts(version="1.2", outdated=True, newest="1.3")), "1.2 → 1.3")
        self.assertEqual(gd.version_text(facts(version="1.2")), "1.2")
        self.assertEqual(gd.version_text(facts(version="Unknown")), "")
        self.assertEqual(gd.version_text(facts(version="1.2", outdated=True, newest="")), "1.2")


class RowTests(unittest.TestCase):
    def setUp(self):
        self.items = gd.cards([
            facts("calm-old", 0, word="On", modified=100),
            facts("update", 1, word="On", outdated=True, newest="2", modified=500),
            facts("clash", 2, word="On", conflicts=1, partners=("update",), modified=300),
            facts("calm-new", 3, word="Off", modified=900),
            facts("undated", 4, word="On"),
        ])

    def test_attention_lists_conflicts_before_updates(self):
        self.assertEqual([c.facts.name for c in gd.needs_attention(self.items)], ["clash", "update"])

    def test_recent_is_newest_first_and_leaves_flagged_rows_out(self):
        self.assertEqual([c.facts.name for c in gd.recently_changed(self.items)], ["calm-new", "calm-old"])

    def test_limits(self):
        many = gd.cards([facts(f"m{i}", i, conflicts=1, modified=i + 1) for i in range(80)])
        self.assertEqual(len(gd.needs_attention(many)), gd.ATTENTION_LIMIT)
        calm = gd.cards([facts(f"c{i}", i, modified=i + 1) for i in range(80)])
        recent = gd.recently_changed(calm)
        self.assertEqual(len(recent), gd.RECENT_LIMIT)
        self.assertEqual(recent[0].facts.name, "c79")


class HealthTests(unittest.TestCase):
    def test_counts_and_unknowns(self):
        rows = [facts("a", is_mod=True, word="On", outdated=True, conflicts=0),
                facts("b", is_mod=True, word="On", outdated=False, conflicts=1),
                facts("c", is_mod=True, word="Off", outdated=False, conflicts=0),
                facts("d", is_mod=True, word="Not recorded", outdated=False, conflicts=0),
                facts("folder", word="Storage folder")]
        h = gd.health(rows)
        self.assertEqual((h["count"], h["on"], h["off"], h["unrecorded"], h["folders"]), (5, 2, 1, 1, 1))
        self.assertEqual((h["outdated"], h["conflicts"]), (1, 1))

    def test_unchecked_stays_none(self):
        h = gd.health([facts("a", is_mod=True, word="On")])
        self.assertIsNone(h["outdated"])
        self.assertIsNone(h["conflicts"])
        self.assertEqual(gd.count_text(h["outdated"]), "Not checked")
        self.assertEqual(gd.count_text(0), "0")

    def test_bar_parts_sum_to_one_and_never_exceed_the_mods(self):
        h = gd.health([facts("a", is_mod=True, word="On", outdated=True, conflicts=0),
                       facts("b", is_mod=True, word="On", outdated=False, conflicts=1),
                       facts("c", is_mod=True, word="On", outdated=False, conflicts=0),
                       facts("d", is_mod=True, word="Off", outdated=False, conflicts=0)])
        parts = gd.bar_parts(h)
        self.assertAlmostEqual(sum(parts), 1.0)
        self.assertTrue(all(p >= 0 for p in parts))
        self.assertEqual(parts, (.25, .25, .25, .25, 0.0))
        self.assertIsNone(gd.bar_parts(gd.health([facts("folder", word="Storage folder")])))
        # Even a sloppy count cannot push the bar past the mods that are on.
        crowded = {"on": 2, "off": 0, "unrecorded": 0, "outdated": 5, "conflicts": 5}
        self.assertAlmostEqual(sum(gd.bar_parts(crowded)), 1.0)
        self.assertTrue(all(p >= 0 for p in gd.bar_parts(crowded)))


class TileTests(unittest.TestCase):
    def test_all_games_first_then_biggest(self):
        rows = [facts("a", game="Skyrim"), facts("b", game="Skyrim", conflicts=1), facts("c", game="Cyberpunk"),
                facts("d", game="Skyrim", outdated=True), facts("e", game="Unverified")]
        found = gd.tiles(rows)
        self.assertEqual([t.name for t in found], [gd.ALL_GAMES, "Skyrim", "Cyberpunk", "Unverified"])
        self.assertEqual([(t.count, t.flagged) for t in found], [(5, 2), (3, 2), (1, 0), (1, 0)])

    def test_empty(self):
        self.assertEqual(gd.tiles([]), [gd.Tile(gd.ALL_GAMES, 0, 0)])

    def test_managers_text(self):
        self.assertEqual(gd.managers_text([facts(manager="Vortex"), facts(manager="Vortex")]), "Vortex")
        self.assertEqual(gd.managers_text([facts(manager="MO2"), facts(manager="Vortex")]), "MO2, Vortex")
        self.assertEqual(gd.managers_text([facts(manager=m) for m in ("A", "B", "C", "D")]), "A, B and 2 more")
        self.assertEqual(gd.managers_text([]), "")


if __name__ == "__main__":
    unittest.main()
