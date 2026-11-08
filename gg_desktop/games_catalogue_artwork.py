"""Automatic covers across launcher catalogues, Steam and Wikipedia.

Only public game titles/IDs are used. Provider account tokens are never sent to
image hosts. A native game icon remains available while a poster is loading.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from gg_desktop.game_artwork import Artwork, MAX_IMAGE_BYTES, _save_picture, game_id, image_from_bytes, local_artwork, official_artwork, read_image
from gg_desktop import game_artwork as _art_storage
from gg_desktop.games_http import ProviderError, json_request

MEDIA_ROOTS = ("steamstatic.com", "epicgames.com", "unrealengine.com", "gog-statics.com", "gog.com", "ea.com", "eaassets-a.akamaihd.net", "media.contentapi.ea.com", "wikimedia.org")
REFERENCE_TITLES = {
    "cyberpunk2077", "baldursgate3", "thewitcher3wildhunt", "thewitcher3", "witcher3",
    "starfield", "skyrimspecialedition", "skyrimse", "reddeadredemption2", "rdr2",
    "callofdutyblackops6", "eldenring", "helldivers2", "dragonagetheveilguard", "dragonageveilguard",
}


def title_key(value):
    return "".join(character for character in value.casefold() if character.isalnum())


def reference_available(name):
    return title_key(name) in REFERENCE_TITLES


def checked_media(url):
    value = urlsplit(url)
    if (value.scheme != "https" or value.port not in (443, None) or value.username or value.password
            or not value.hostname or not any(value.hostname == root or value.hostname.endswith("."+root) for root in MEDIA_ROOTS)
            or len(url) > 4000 or any(word in value.query.casefold() for word in ("access_token", "refresh_token", "authorizationcode"))):
        raise ValueError("Artwork address is outside the supported public media hosts.")


class MediaRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_media(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def media_request(url):
    checked_media(url)
    # No account headers, cookies or referer are attached to media requests.
    with build_opener(MediaRedirects()).open(Request(url, headers={"User-Agent": "GameGrave-Games/0.2.14"}), timeout=6) as response:
        checked_media(response.geturl())
        value = response.read(MAX_IMAGE_BYTES + 1)
    return image_from_bytes(value)


def cached_artwork(game, roots=()):
    art = local_artwork(game, roots)
    if art.image is not None:
        return art
    path = _art_storage.artwork_dir()/(game_id(game)+".catalogue.png")
    try:
        return Artwork(read_image(path), "Cached catalogue artwork")
    except (OSError, ValueError):
        return Artwork()


def remote_artwork(game, facts=None, *, canceled=lambda: False, get_json=json_request, get_image=media_request):
    facts = facts or {}
    if canceled():
        return Artwork()
    if not facts.get("owned"):
        from core import _has_reparse_component
        if "open_folder" not in game.capabilities or not game.install_path or not Path(game.install_path).is_dir() or _has_reparse_component(game.install_path):
            return Artwork()
    url = facts.get("artwork_url")
    if isinstance(url, str) and url:
        if url.startswith("//"):
            url = "https:"+url
        try:
            image = get_image(url)
            if not canceled():
                _save_picture(game, image, "catalogue")
                return Artwork(image, game.launcher + " catalogue artwork")
        except (OSError, ValueError, RuntimeError):
            pass
    if canceled():
        return Artwork()
    try:
        # An immutable artwork-only view permits title lookup for a verified
        # owned, uninstalled game. No installation/launch capability is exposed
        # to the library or native action controller.
        art_game = replace(game, capabilities=(*game.capabilities, "open_folder")) if facts.get("owned") and "open_folder" not in game.capabilities else game
        art = official_artwork(art_game, canceled=canceled)
        if art.image is not None:
            return art
    except (OSError, ValueError, TypeError):
        pass
    if canceled():
        return Artwork()
    try:
        query = urlencode(dict(action="query", format="json", titles=game.name, prop="pageimages|pageprops", piprop="thumbnail", pithumbsize=600, redirects=1))
        result = get_json("https://en.wikipedia.org/w/api.php?"+query, hosts={"en.wikipedia.org"})
        pages = result.get("query", {}).get("pages", {})
        for page in pages.values() if isinstance(pages, dict) else ():
            if not isinstance(page, dict) or "missing" in page or "disambiguation" in page.get("pageprops", {}):
                continue
            canonical = re.sub(r"\s*\(video game\)\s*$", "", str(page.get("title", "")), flags=re.I)
            if title_key(canonical) != title_key(game.name):
                continue
            source = page.get("thumbnail", {}).get("source")
            if isinstance(source, str) and not canceled():
                image = get_image(source)
                if not canceled():
                    _save_picture(game, image, "catalogue")
                    return Artwork(image, "Wikipedia game artwork")
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return Artwork()
