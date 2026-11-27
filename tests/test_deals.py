"""Deals: parsing CheapShark and GG.deals answers, the wishlist and price-drop notices. No network."""
import unittest

from gg_desktop import deals_core as dc

STORES = [{"storeID": "1", "storeName": "Steam", "isActive": 1}, {"storeID": "7", "storeName": "GOG", "isActive": 1},
          {"storeID": "15", "storeName": "Fanatical", "isActive": 1}, {"storeID": "99", "storeName": "Closed", "isActive": 0}]
GAME = {"info": {"title": "Portal 2", "steamAppID": "620", "thumb": "https://cdn.example/p2.jpg"},
        "cheapestPriceEver": {"price": "0.99", "date": 1700000000},
        "deals": [{"storeID": "1", "dealID": "a%2B1", "price": "9.99", "retailPrice": "9.99", "savings": "0.000000"},
                  {"storeID": "15", "dealID": "f1", "price": "1.99", "retailPrice": "9.99", "savings": "80.08"},
                  {"storeID": "99", "dealID": "x", "price": "0.50", "retailPrice": "9.99", "savings": "95"},
                  {"storeID": "7", "dealID": "g1", "price": "bad"}]}


def game(price, store="Fanatical", ever=None, savings=0):
    return dc.GameDeals("612", "Portal 2", "620", "", [dc.Offer(store, "15", price, 9.99, savings, "https://x")], ever)


class Parsing(unittest.TestCase):
    def test_game_offers_cheapest_first_inactive_and_broken_left_out(self):
        stores = dc.parse_stores(STORES)
        self.assertNotIn("99", stores)
        g = dc.parse_game("612", GAME, stores)
        self.assertEqual([(o.store, o.price) for o in g.offers], [("Fanatical", 1.99), ("Steam", 9.99)])
        self.assertEqual(g.best.savings, 80)
        self.assertTrue(g.best.url.startswith("https://www.cheapshark.com/redirect?dealID="))
        self.assertEqual(g.lowest_ever, 0.99)
        self.assertIn("Cheapest found: $1.99 at Fanatical (80% off $9.99). Lowest ever: $0.99", dc.summary(g))
        self.assertIsNone(dc.parse_game("1", {"nope": 1}, stores))

    def test_search_and_many(self):
        hits = dc.parse_search([{"gameID": "612", "steamAppID": "620", "cheapest": "1.99", "external": "Portal 2",
                                 "thumb": "t"}, {"bad": 1}, "junk"])
        self.assertEqual(hits, [dc.Hit("612", "Portal 2", "620", 1.99, "t")])
        many = dc.parse_games({"612": GAME, "13": None}, dc.parse_stores(STORES))
        self.assertEqual(list(many), ["612"])
        self.assertEqual(dc.parse_search({"error": "x"}), [])

    def test_ggdeals_keyshops(self):
        data = {"success": True, "data": {"620": {"title": "Portal 2", "url": "https://gg.deals/game/portal-2/",
                                                   "prices": {"currentRetail": "9.99", "currentKeyshops": "1.20",
                                                              "historicalRetail": "0.99", "historicalKeyshops": "0.60",
                                                              "currency": "USD"}}}}
        k = dc.parse_ggdeals(data, "620")
        self.assertEqual((k.current, k.lowest, k.retail_lowest, k.currency), (1.20, 0.60, 0.99, "USD"))
        self.assertIsNone(dc.parse_ggdeals({"success": False}, "620"))
        self.assertIsNone(dc.parse_ggdeals({"success": True, "data": {"620": None}}, "620"))

    def test_urls_and_hosts(self):
        self.assertTrue(dc.api_allowed(dc.search_url("Elden Ring")))
        self.assertIn("title=Elden+Ring", dc.search_url("Elden Ring"))
        self.assertTrue(dc.api_allowed(dc.ggdeals_url(["620"], "abcdefghijklmnop")))
        self.assertFalse(dc.api_allowed("http://www.cheapshark.com/api"))
        self.assertFalse(dc.api_allowed("https://evil.example/api"))
        self.assertEqual(dc.games_url(["1", "2"]), "https://www.cheapshark.com/api/1.0/games?ids=1,2")
        names = [n for n, _ in dc.reseller_links("Elden Ring")]
        self.assertEqual(names[:3], ["G2A", "Kinguin", "Eneba"])
        self.assertTrue(all(u.startswith("https://") for _, u in dc.reseller_links("x")))
        self.assertTrue(dc.valid_ggdeals_key("A1b2C3d4E5f6G7h8"))
        self.assertFalse(dc.valid_ggdeals_key("short"))
        self.assertEqual(dc.price_text(0), "Free")
        self.assertEqual(dc.price_text(1234.5), "$1,234.50")
        self.assertEqual(dc.price_text(None), "—")

    def test_never_says_safe_or_guaranteed(self):
        text = (dc.RESELLER_WARNING + dc.summary(game(1.99))).casefold()
        for banned in ("safe", "guarantee", "cheapest anywhere"):
            self.assertNotIn(banned, text)


class Wishlist(unittest.TestCase):
    def test_add_remove_target_and_cap(self):
        items = dc.add_item([], game(4.99), target=3, now=10)
        self.assertEqual((items[0]["best"], items[0]["notified"], items[0]["target"]), (4.99, 4.99, 3.0))
        items = dc.add_item(items, game(4.99), target=2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["target"], 2.0)
        self.assertEqual(dc.remove_item(items, "612"), [])
        full = [{"game_id": str(n)} for n in range(dc.MAX_WISHLIST)]
        with self.assertRaises(ValueError):
            dc.add_item(full, game(1))
        settings = dc.with_wishlist({}, items)
        self.assertEqual(dc.wishlist(settings)[0]["title"], "Portal 2")
        self.assertEqual(dc.wishlist({dc.WISHLIST_KEY: [{"x": 1}, "bad"]}), [])

    def test_drops_notify_once_and_only_when_real(self):
        items = dc.add_item([], game(10.0))
        self.assertIsNone(dc.drop_message(items[0], game(9.80)), "20 cents is not news")
        items, news = dc.refreshed(items, {"612": game(7.50, savings=25)})
        self.assertEqual(len(news), 1)
        self.assertIn("$7.50 at Fanatical (was $10.00)", news[0][1])
        items, news = dc.refreshed(items, {"612": game(7.50)})
        self.assertEqual(news, [], "the same price never notifies twice")
        items, news = dc.refreshed(items, {"612": game(12.0)})
        self.assertEqual((news, items[0]["notified"]), ([], 12.0))
        items, news = dc.refreshed(items, {"612": game(10.0)})
        self.assertEqual(len(news), 1, "a real drop after a rise is news again")

    def test_target_and_lowest_ever(self):
        items = dc.add_item([], game(20.0), target=15)
        _, news = dc.refreshed(items, {"612": game(14.99, ever=14.99)})
        self.assertIn("at or under your target", news[0][1])
        self.assertIn("Lowest price CheapShark has seen", news[0][1])

    def test_missing_answers_keep_old_price_and_checks_are_spaced(self):
        items = dc.add_item([], game(5.0))
        same, news = dc.refreshed(items, {})
        self.assertEqual((same, news), (items, []))
        self.assertTrue(dc.due({}, now=1_800_000_000))
        self.assertFalse(dc.due({dc.CHECKED_KEY: 1000}, now=1000 + 3600))
        self.assertTrue(dc.due({dc.CHECKED_KEY: 1000}, now=1000 + dc.WATCH_HOURS * 3600))
        self.assertEqual(len(dc.batches([{"game_id": str(n)} for n in range(60)])), 3)


if __name__ == "__main__":
    unittest.main()
