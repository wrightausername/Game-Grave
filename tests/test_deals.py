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


class Storefront(unittest.TestCase):
    DEALS = [{"internalName": "PORTAL2", "title": "Portal 2", "dealID": "d1", "storeID": "15", "gameID": "612",
              "salePrice": "1.99", "normalPrice": "9.99", "savings": "80.08", "steamRatingText": "Overwhelmingly Positive",
              "steamRatingPercent": "98", "metacriticScore": "95", "steamAppID": "620", "thumb": "https://t/p2.jpg"},
             {"title": "Portal 2", "dealID": "d2", "storeID": "1", "gameID": "612", "salePrice": "9.99"},
             {"title": "Closed store", "dealID": "d3", "storeID": "99", "gameID": "5", "salePrice": "1"},
             {"title": "Giveaway", "dealID": "d4", "storeID": "7", "gameID": "77", "salePrice": "0.00",
              "normalPrice": "19.99", "savings": "100", "steamAppID": None, "thumb": "https://t/g.jpg"}]

    def test_deals_parse_one_card_per_game_and_skip_closed_stores(self):
        cards = dc.parse_deals(self.DEALS, dc.parse_stores(STORES))
        self.assertEqual([(c.title, c.store, c.price, c.savings) for c in cards],
                         [("Portal 2", "Fanatical", 1.99, 80), ("Giveaway", "GOG", 0.0, 100)])
        self.assertEqual((cards[0].rating, cards[0].rating_pct, cards[0].metacritic), ("Overwhelmingly Positive", 98, 95))
        self.assertTrue(cards[0].url.startswith("https://www.cheapshark.com/redirect?dealID=d1"))
        self.assertEqual(dc.parse_deals({"oops": 1}, {}), [])

    def test_art_store_icons_rows_and_meter(self):
        self.assertEqual(dc.art_url("620"), "https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg")
        self.assertEqual(dc.art_url("", "https://t/x.jpg"), "https://t/x.jpg")
        icons = dc.parse_store_icons([{"storeID": "1", "images": {"icon": "/img/stores/icons/0.png"}}, {"storeID": "2"}])
        self.assertEqual(icons, {"1": "https://www.cheapshark.com/img/stores/icons/0.png"})
        self.assertTrue(all(dc.api_allowed(dc.deals_list_url(params)) for *_, params in dc.FRONT))
        self.assertIn("sortBy=Deal%20Rating", dc.deals_list_url(dc.FRONT[0][3]))
        g = dc.parse_game("612", GAME, dc.parse_stores(STORES))
        self.assertEqual(dc.meter(g), (1.99, 9.99, 0.99))
        self.assertIsNone(dc.meter(dc.GameDeals("1", "x", "", "")))
        for _key, title, note, _p in dc.FRONT:
            self.assertNotIn("safe", (title + note).casefold())


class FreeAlerts(unittest.TestCase):
    def card(self, gid, price=0.0, title=None):
        return dc.Deal(gid, title or f"Game {gid}", "", price, 19.99, 100, "GOG", "7", "https://x", "", 0, 0, "")

    def test_new_giveaways_once_and_today_list(self):
        settings, fresh = dc.free_update({}, [self.card("1"), self.card("2"), self.card("3", 4.99)], now=50)
        self.assertEqual([d.game_id for d in fresh], ["1", "2"], "only $0 games count")
        self.assertEqual([f["title"] for f in settings[dc.FREE_NOW_KEY]], ["Game 1", "Game 2"])
        self.assertEqual(settings[dc.FREE_CHECKED_KEY], 50)
        settings, fresh = dc.free_update(settings, [self.card("1"), self.card("4")])
        self.assertEqual([d.game_id for d in fresh], ["4"])
        self.assertEqual(dc.free_message([self.card("4", title="Hades")])[0], "Free to keep: Hades")
        self.assertIn("3 games are free", dc.free_message([self.card(str(n)) for n in range(3)])[0])
        self.assertIsNone(dc.free_message([]))
        self.assertNotIn("safe", " ".join(dc.free_message([self.card("9")])).casefold())
        self.assertTrue(dc.free_alerts_on({}))
        self.assertFalse(dc.free_alerts_on({dc.FREE_ALERTS_KEY: False}))
        self.assertTrue(dc.free_due({}, now=1_800_000_000))

    def test_recent_drops_kept_for_today(self):
        s = dc.remember_drops({}, [("Hades", "$5 at GOG")], now=10)
        s = dc.remember_drops(s, [("Doom", "$3 at Steam")], now=20, keep=1)
        self.assertEqual(s[dc.DROPS_KEY], [{"title": "Doom", "message": "$3 at Steam", "at": 20}])


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
