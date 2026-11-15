import unittest
from types import SimpleNamespace as NS

from gg_desktop import gamenight_core as gn


def game(name, launcher="Steam", app_id="", size=None):
    return NS(name=name, launcher=launcher, app_id=app_id, size_bytes=size)


class GameNight(unittest.TestCase):
    def test_code_round_trip_inside_a_chat_message(self):
        code = gn.make_code("Alex", [game("Helldivers 2", app_id="553850", size=100), game("Fortnite", "Epic")])
        broken = "here you go\n" + code[:30] + "\n" + code[30:] + " gl hf"
        friend = gn.read_code(broken)
        self.assertEqual(friend.name, "Alex")
        self.assertEqual([g["n"] for g in friend.games], ["Helldivers 2", "Fortnite"])
        self.assertEqual(friend.games[1]["a"], "", "only Steam games carry an app id")
        with self.assertRaises(gn.GameNightError):
            gn.read_code("GGSQ1-notthis")
        with self.assertRaises(gn.GameNightError):
            gn.make_code("", [])

    def test_overlap(self):
        mine = gn.game_entries([game("Helldivers 2", app_id="553850", size=100), game("Lethal Company", app_id="1966720"),
                                game("Solo Game", app_id="1")])
        jay = gn.Friend("Jay", gn.game_entries([game("HELLDIVERS™ 2", app_id="553850"), game("Fortnite", "Epic")]))
        sam = gn.Friend("Sam", gn.game_entries([game("Helldivers 2", app_id="553850"), game("Lethal Company", app_id="1966720"),
                                               game("Fortnite", "Epic")]))
        rows = gn.overlap("Me", mine, [jay, sam])
        self.assertEqual(rows[0].title, "Helldivers 2")
        self.assertTrue(rows[0].everyone)
        lethal = next(r for r in rows if r.title == "Lethal Company")
        self.assertEqual(lethal.missing, ["Jay"])
        fort = next(r for r in rows if r.title == "Fortnite")
        self.assertEqual(fort.missing, ["Me"])
        self.assertNotIn("Solo Game", [r.title for r in rows])
        self.assertIn("can all play 1 game", gn.summary(rows, [jay, sam]))

    def test_modes_and_friends(self):
        self.assertEqual(gn.parse_modes([{"id": 2}]), ("Single-player",))
        self.assertEqual(gn.parse_modes([{"id": 1}, {"id": 38}, {"id": 2}]), ("Online co-op", "Multiplayer"))
        row = gn.Row("X", "1", ["a", "b"], [], modes=("Single-player",))
        self.assertFalse(gn.together(row))
        self.assertTrue(gn.together(gn.Row("Y", "", ["a", "b"], [])), "unknown modes never hide a game")
        friends = []
        for i in range(10):
            friends = gn.with_friend(friends, gn.Friend(f"F{i}", []), i)
        self.assertEqual(len(friends), gn.MAX_FRIENDS)
        friends = gn.with_friend(friends, gn.Friend("f9", [{"n": "A"}]), 11)
        self.assertEqual(sum(1 for f in friends if f.name.casefold() == "f9"), 1)
        s = gn.friends_to({}, friends)
        self.assertEqual([f.name for f in gn.friends_from(s)], [f.name for f in friends])


if __name__ == "__main__":
    unittest.main()


class StoreModes(unittest.TestCase):
    def test_fetch_is_cached_bounded_and_stops_for_games(self):
        import json as j
        calls = []

        def opener(url):
            calls.append(url)
            app = url.split("appids=")[1].split("&")[0]
            return j.dumps({app: {"success": True, "data": {"categories": [{"id": 38}]}}}).encode()
        cache = gn.fetch_modes(["1", "2", "x", "1"], {"2": ("Co-op",)}, opener=opener, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache["1"], ("Online co-op",))
        none = gn.fetch_modes(["3"], {}, opener=opener, sleep=lambda s: None, game_running=lambda: True)
        self.assertNotIn("3", none)
        rows = gn.with_modes([gn.Row("A", "1", ["a", "b"], [])], cache)
        self.assertEqual(rows[0].modes, ("Online co-op",))
