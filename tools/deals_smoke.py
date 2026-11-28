"""Native Qt check of the Deals tab with stand-in price answers: the sidebar row, search, every store's price cheapest
first, Open store opens the browser, key reseller searches without a key and GG.deals prices with one, the wishlist with
a target, the quiet watch (never while a game runs, never twice for the same price), and the subtle notice.
Then, unless --offline, a REAL check against CheapShark's live API so the parsing is proven on today's answers."""
from __future__ import annotations

import argparse
import faulthandler
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

STORES = [{"storeID": "1", "storeName": "Steam", "isActive": 1, "images": {"icon": "/img/stores/icons/0.png"}},
          {"storeID": "15", "storeName": "Fanatical", "isActive": 1, "images": {"icon": "/img/stores/icons/14.png"}},
          {"storeID": "7", "storeName": "GOG", "isActive": 1, "images": {"icon": "/img/stores/icons/6.png"}}]
DEALS = [{"title": f"Deal Game {n}", "dealID": f"deal{n}", "storeID": ("1", "15", "7")[n % 3], "gameID": str(700 + n),
          "salePrice": f"{n + 0.99:.2f}", "normalPrice": "29.99", "savings": str(90 - n * 5), "steamAppID": str(1000 + n),
          "steamRatingText": "Very Positive", "steamRatingPercent": "91", "thumb": "https://img.test/t.jpg"} for n in range(6)]
FREE = [{"title": "Free Game", "dealID": "free1", "storeID": "7", "gameID": "800", "salePrice": "0.00",
         "normalPrice": "19.99", "savings": "100", "steamAppID": "", "thumb": "https://img.test/f.jpg"}]
SEARCH = [{"gameID": "612", "steamAppID": "620", "cheapest": "1.99", "external": "Portal 2", "thumb": "https://img.test/p2.jpg"},
          {"gameID": "613", "steamAppID": "", "cheapest": "4.99", "external": "Portal 2 Soundtrack", "thumb": ""}]


def game_answer(price):
    return {"info": {"title": "Portal 2", "steamAppID": "620", "thumb": "https://img.test/p2.jpg"},
            "cheapestPriceEver": {"price": "0.99", "date": 1700000000},
            "deals": [{"storeID": "1", "dealID": "steam1", "price": "9.99", "retailPrice": "9.99", "savings": "0"},
                      {"storeID": "15", "dealID": "fan1", "price": price, "retailPrice": "9.99", "savings": "80"},
                      {"storeID": "7", "dealID": "gog1", "price": "4.99", "retailPrice": "9.99", "savings": "50"}]}


def main():
    faulthandler.dump_traceback_later(240, exit=True)   # a hang prints where it stuck instead of stalling CI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtWidgets import QApplication
    import core
    from gg_desktop import deals_core as dc, deals_net, deals_page, nav_groups
    from gg_desktop.app import CrimsonWindow

    app = QApplication.instance() or QApplication([])

    def settle(ms=40):
        app.processEvents()
        QTest.qWait(ms)
        app.processEvents()

    def wait_for(test, seconds=15):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents(QEventLoop.AllEvents, 50)
            if test():
                return
            time.sleep(0.02)
        raise AssertionError("timed out")

    image = QImage(460, 215, QImage.Format_RGB32)
    image.fill(QColor("#13bcf5"))
    raw = QByteArray()
    buffer = QBuffer(raw)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    png = bytes(raw)

    price = {"fan": "1.99"}
    calls = []

    def fake_json(url):
        calls.append(url)
        if not dc.api_allowed(url):
            raise AssertionError("asked a host outside the allowlist: " + url)
        if url.endswith("/stores"):
            return STORES
        if "/deals?" in url:
            return FREE if "upperPrice=0" in url else DEALS
        if "games?title=" in url:
            return SEARCH
        if "games?ids=" in url:
            return {"612": game_answer(price["fan"])}
        if "games?id=" in url:
            return game_answer(price["fan"])
        if "store.steampowered.com/api/storesearch" in url:
            term = url.split("term=")[1].split("&")[0]
            return {"items": [{"id": 777, "name": "Free Game"}, {"id": 778, "name": "Free Game Deluxe"}]} \
                if term == "Free%20Game" else {"items": []}
        if "store.steampowered.com/api/appdetails" in url:
            app = url.split("appids=")[1].split("&")[0]
            data = {"short_description": f"A test game number {app} about racing."}
            if "filters=basic" not in url:
                data["screenshots"] = [{"path_thumbnail": f"https://shared.akamai.steamstatic.com/s{n}.600x338.jpg",
                                        "path_full": f"https://shared.akamai.steamstatic.com/s{n}.1920x1080.jpg"}
                                       for n in range(3)]
                data["movies"] = [{"name": "Launch trailer", "thumbnail": "https://shared.akamai.steamstatic.com/m.jpg",
                                   "mp4": {"max": "https://video.akamai.steamstatic.com/m.mp4"}}]
            return {app: {"success": True, "data": data}}
        if "api.gg.deals" in url:
            assert "key=TESTKEY0123456789" in url
            return {"success": True, "data": {"620": {"title": "Portal 2", "url": "https://gg.deals/game/portal-2/",
                                                       "prices": {"currentKeyshops": "1.10", "historicalKeyshops": "0.55",
                                                                  "historicalRetail": "0.99", "currency": "USD"}}}}
        raise AssertionError("unexpected " + url)

    with tempfile.TemporaryDirectory(prefix="GG-deals-") as temp:
        root = Path(temp)
        opened, notices = [], []
        stack = ExitStack()
        for target, options in (
            ("core.config_dir", dict(return_value=root / "Config")),
            ("gg_desktop.tools_page.get_activity", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.ready_room_services.fetch_one", dict(side_effect=OSError("offline QA"))),
            ("gg_desktop.deals_net.get_json", dict(side_effect=fake_json)),
            ("gg_desktop.deals_net.image", dict(return_value=png)),
            ("gg_desktop.deals_page.QDesktopServices.openUrl", dict(side_effect=lambda u: opened.append(u.toString()))),
            ("gg_desktop.comfort.notify", dict(side_effect=lambda w, t, x, *a, **k: notices.append((t, x)))),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=True))
        with stack:
            core.save_settings(core.default_settings())
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 760)
            settle()

            # Sidebar: Deals is one of the everyday entries at the top, after Games and Mods.
            first = [e for s, e, _r, _p in nav_groups.entries() if not s and not _p]
            assert first == ["Home", "Games", "Mods", "Deals"], first
            assert "Deals" in window.nav_buttons
            window.navigate("Deals")
            settle(200)
            assert window.current_route == "Deals"
            w = window.deals_page_widgets
            assert w.search.accessibleName() and w.target.accessibleName()
            assert not w.buy.isEnabled() and not w.watch.isEnabled()

            # The storefront: three rows of cards with pictures, badges and store icons (owner, 2026-11-27).
            def shown_cards():
                return [c for c in window.findChildren(deals_page.DealCard) if c.isVisible()]
            wait_for(lambda: len(shown_cards()) >= 7)
            settle(100)
            cards = shown_cards()
            assert w.stack.currentIndex() == 0
            titles = [c.deal.title for c in cards]
            assert "Free Game" in titles and "Deal Game 0" in titles, titles
            assert sum(1 for c in cards if c.deal.price == 0) >= 1
            wait_for(lambda: all(c.art.pixmap() is not None and not c.art.pixmap().isNull() for c in cards))
            # What each game is: Steam's short description on the card (games not on Steam say so).
            wait_for(lambda: all("racing" in c.about.text() for c in cards if c.deal.steam_app_id), 20)
            free_card = next(c for c in cards if c.deal.title == "Free Game")
            wait_for(lambda: "777" in free_card.about.text(), 20)          # matched by its exact name on Steam
            for c in cards:                                                 # three whole lines, never cut mid-line
                lines = c.about.fontMetrics().boundingRect(0, 0, c.about.width(), 10000, int(Qt.TextWordWrap),
                                                           c.about.text()).height()
                assert lines <= c.about.height(), (c.deal.title, lines, c.about.height())
            assert "racing" in next(c for c in cards if c.deal.steam_app_id).toolTip()
            settle(200)
            assert window.grab().save(str(args.output / "deals-front-1280.png"))
            first = next(c for c in cards if c.deal.title == "Deal Game 0")
            QTest.mouseClick(first, Qt.LeftButton)
            wait_for(lambda: deals_page.state(window).game is not None)
            settle(100)
            assert w.stack.currentIndex() == 1 and w.meter.isVisible()
            # Screenshots and trailers: a strip under the prices, and a viewer with Back / Next.
            assert not w.side.isVisible(), "the game's page gets the whole width"
            assert w.back.text().startswith("←") and w.back.isVisible()
            wait_for(lambda: w.media.isVisible() and len(getattr(w.media, "items", [])) == 4, 20)
            wait_for(lambda: w.hero.source is not None and "Screenshot 1" in w.hero_caption.text(), 20)
            assert "Action" in w.info_line.text() or w.info_line.text() == "", w.info_line.text()
            w.media.findChildren(QPushButton)[2].click()                    # another screenshot into the big area
            wait_for(lambda: "Screenshot 2" in w.hero_caption.text())
            assert w.price_panel.isVisible() and w.table.height() >= w.table.rowCount() * 40
            assert w.media.items[0][0] == "video" and "1 trailer and 3 screenshots" in w.media.caption.text()
            assert "racing" in w.about_line.text(), w.about_line.text()
            from gg_desktop import deals_media
            with patch("gg_desktop.deals_page.open_url"):
                viewer = deals_media.open_viewer(window, w.media, first.deal.title, 1, lambda url, size, label, after:
                                                 deals_page.picture(window, url, size, label, whole=True, after=after))
                wait_for(lambda: viewer.view.pixmap() is not None and not viewer.view.pixmap().isNull())
                assert "2 of 4" in viewer.caption.text(), viewer.caption.text()
                viewer.next.click()
                settle()
                assert "3 of 4" in viewer.caption.text()
                assert viewer.grab().save(str(args.output / "deals-media-viewer.png"))
                viewer.close()
            assert window.grab().save(str(args.output / "deals-game-media.png"))
            window.resize(960, 760)
            settle(200)
            assert window.grab().save(str(args.output / "deals-game-960.png"))
            window.resize(1280, 760)
            settle(100)
            w.back.click()
            settle()
            assert w.side.isVisible() and w.stack.currentIndex() == 0
            QTest.mouseClick(first, Qt.LeftButton)
            wait_for(lambda: w.stack.currentIndex() == 1)
            QTest.keyClick(w.stack.currentWidget(), Qt.Key_Escape)
            settle(300)                      # a price lookup finishing after Esc must not reopen the page
            assert w.stack.currentIndex() == 0, "Esc goes back to the deals"
            QTest.mouseClick(first, Qt.LeftButton)
            wait_for(lambda: w.stack.currentIndex() == 1)
            w.back.click()
            settle()
            assert w.stack.currentIndex() == 0
            deals_page.state(window).game = None
            deals_page.show_game(window)

            # Search: results with "from" prices; the first is opened with every store cheapest first.
            QTest.keyClicks(w.search, "Portal 2")
            QTest.keyClick(w.search, Qt.Key_Return)
            wait_for(lambda: w.results.count() == 2)
            assert "from $1.99" in w.results.item(0).text()
            wait_for(lambda: deals_page.state(window).game is not None)
            settle(100)
            assert w.title.text() == "Portal 2" and w.stack.currentIndex() == 1
            assert w.best.text() == "$1.99 at Fanatical", w.best.text()
            assert [w.table.item(r, 0).text() for r in range(w.table.rowCount())] == ["Fanatical", "GOG", "Steam"]
            assert "Lowest ever: $0.99" in w.summary.text()
            wait_for(lambda: w.art.pixmap() is not None and not w.art.pixmap().isNull())

            # Open store opens the store page through CheapShark's link; nothing is bought.
            w.buy.click()
            w.table.cellWidget(2, 4).click()
            assert opened[-2].startswith("https://www.cheapshark.com/redirect?dealID=fan1"), opened
            assert opened[-1].endswith("dealID=steam1"), opened

            # Without a GG.deals key: reseller searches, labelled, no made-up number.
            assert w.resellers.isVisible() and "free GG.deals API key" in w.keyshop.text()
            names = [w.reseller_row.itemAt(n).widget().text() for n in range(w.reseller_row.count())
                     if w.reseller_row.itemAt(n).widget()]
            assert names[:3] == ["G2A", "Kinguin", "Eneba"] and "Add GG.deals key…" in names, names
            assert window.grab().save(str(args.output / "deals-game-1280.png"))

            # With a key: GG.deals keyshop prices, still labelled with the warning.
            with patch("gg_desktop.deals_net.load_key", return_value="TESTKEY0123456789"):
                deals_page.pick(window, "612")
                wait_for(lambda: deals_page.state(window).keyshops is not None)
                settle(100)
                assert "from $1.10 now (lowest seen $0.55)" in w.keyshop.text(), w.keyshop.text()
                assert any(u.startswith("https://api.gg.deals/") for u in calls)
                assert window.grab().save(str(args.output / "deals-resellers-1280.png"))
            deals_page.state(window).keyshops = None
            deals_page.show_game(window)

            # Wishlist with a target.
            w.target.setValue(1.50)
            w.watch.click()
            settle()
            items = dc.wishlist(window.settings)
            assert len(items) == 1 and items[0]["target"] == 1.5 and items[0]["best"] == 1.99
            assert w.watch.text() == "Update wishlist"
            assert "Portal 2" in w.wish.item(0).text() and "target $1.50" in w.wish.item(0).text()

            # Free game alerts: one quiet notice for a new giveaway, never twice for the same one (owner, 2026-11-27).
            assert w.free_alerts.isChecked() and dc.free_alerts_on(window.settings)
            window.settings = dict(window.settings, **{dc.FREE_CHECKED_KEY: 0})
            assert deals_page.watch_tick(window) is True
            wait_for(lambda: not getattr(deals_page.state(window), "checking_free", False) and not deals_page.state(window).checking)
            assert notices and notices[-1][0] == "Free to keep: Free Game", notices
            assert window.settings[dc.FREE_NOW_KEY][0]["title"] == "Free Game"
            window.settings = dict(window.settings, **{dc.FREE_CHECKED_KEY: 0})
            deals_page.watch_tick(window)
            wait_for(lambda: not getattr(deals_page.state(window), "checking_free", False) and not deals_page.state(window).checking)
            assert len(notices) == 1, ("a giveaway is announced once", notices)
            w.free_alerts.setChecked(False)
            assert not dc.free_alerts_on(window.settings)
            w.free_alerts.setChecked(True)
            notices.clear()

            # The watch: never while a game runs; checks when due; a real drop notifies once, quietly.
            window.settings = dict(window.settings, **{dc.CHECKED_KEY: 0, dc.FREE_CHECKED_KEY: time.time()})
            with patch("gg_desktop.autopsy_ui.game_running", return_value=True):
                assert deals_page.watch_tick(window) is False, "never while a game runs"
            price["fan"] = "1.49"
            assert deals_page.watch_tick(window) is True
            wait_for(lambda: not deals_page.state(window).checking)
            assert len(notices) == 1 and notices[0][0] == "Price drop: Portal 2", notices
            assert window.settings[dc.DROPS_KEY][-1]["title"] == "Portal 2"
            assert "$1.49 at Fanatical (was $1.99)" in notices[0][1] and "target" in notices[0][1]
            assert deals_page.watch_tick(window) is False, "not again until the next six-hour window"
            window.settings = dict(window.settings, **{dc.CHECKED_KEY: 0, dc.FREE_CHECKED_KEY: time.time()})
            assert deals_page.watch_tick(window) is True
            wait_for(lambda: not deals_page.state(window).checking)
            assert len(notices) == 1, "the same price never notifies twice"
            assert "$1.49 at Fanatical" in w.wish.item(0).text()
            assert window.grab().save(str(args.output / "deals-wishlist-1280.png"))

            # Remove, narrow window, everything still fits.
            w.wish.setCurrentRow(0)
            w.remove_wish.click()
            settle()
            assert dc.wishlist(window.settings) == []
            for width in (960, 1440):
                window.resize(width, 720)
                settle(150)
                assert window.page.horizontalScrollBar().maximum() == 0, f"sideways scroll at {width}"
                assert window.grab().save(str(args.output / f"deals-page-{width}.png"))
            assert errors.call_count == 0, errors.call_args_list
            window.close()
            settle()
    print("PASS: Deals tab: Library row, storefront rows with cards, search, stores cheapest first, Open store through CheapShark's link, reseller searches "
          "without a key, GG.deals keyshop prices with one, wishlist with target, watch skipped while playing, one quiet notice "
          "per real drop, remove, no sideways scroll.")

    if args.offline:
        return
    # REAL: today's CheapShark answers must parse.
    with tempfile.TemporaryDirectory(prefix="GG-deals-real-") as temp, patch("core.config_dir", return_value=Path(temp)):
        try:
            hits = deals_net.search("Portal 2")
        except deals_net.DealsError as exc:
            print("SKIP real CheapShark check (service unreachable from the build machine):", exc)
            return
        assert hits and all(h.game_id and h.title for h in hits), hits[:3]
        found = deals_net.game(hits[0].game_id)
        assert found.title and found.offers, found
        assert all(o.store and o.price >= 0 and o.url.startswith("https://www.cheapshark.com/redirect?dealID=") for o in found.offers)
        many = deals_net.games([h.game_id for h in hits[:3]])
        assert many, "batch price check returned nothing"
        rows = deals_net.front()
        assert rows.get("best"), "live storefront 'best deals' row came back empty"
        assert all(d.title and d.price >= 0 and d.url.startswith("https://www.cheapshark.com/redirect?dealID=")
                   for row in rows.values() for d in row)
        about = deals_net.about(["620"], pause=0)
        if about.get("620"):
            print("PASS real Steam description:", about["620"][:120])
        else:
            print("SKIP real Steam description (Steam's store didn't answer from the build machine)")
        print("PASS real storefront rows:", {k: len(v) for k, v in rows.items()}, "e.g.",
              [(d.title, d.price, d.store) for d in rows["best"][:3]])
        print(f"PASS real CheapShark: {len(hits)} results for Portal 2; {found.title}: {dc.summary(found)} "
              f"({len(found.offers)} stores); batch check returned {len(many)} games.")


if __name__ == "__main__":
    main()
