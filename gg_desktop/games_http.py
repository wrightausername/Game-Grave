"""Bounded, credential-scoped HTTP for Games account and artwork providers."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_JSON = 8 * 1024 * 1024


class ProviderError(ValueError):
    pass


class SignInRequired(ProviderError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def checked_url(url, hosts):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.port not in (443, None)
            or parsed.username or parsed.password or len(url) > 18000):
        raise ProviderError("The provider returned an unsupported address.")


def request(url, *, hosts, headers=None, data=None, form=None, limit=MAX_JSON, timeout=10):
    checked_url(url, hosts)
    values = {"User-Agent": "GameGrave-Games/0.2.14", "Accept": "application/json"}
    values.update(headers or {})
    if any(not isinstance(key, str) or not isinstance(value, str) or len(value) > 20000
           or any(char in key+value for char in "\r\n\0") for key, value in values.items()):
        raise ProviderError("The account connection contains an invalid request header. Reconnect it.")
    if form is not None:
        data = urlencode(form).encode()
        values["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        data = json.dumps(data, separators=(",", ":")).encode()
        values["Content-Type"] = "application/json"
    try:
        # Never forward account cookies or bearer tokens through a redirect.
        with build_opener(NoRedirect()).open(Request(url, data=data, headers=values), timeout=timeout) as response:
            checked_url(response.geturl(), hosts)
            raw = response.read(limit + 1)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise SignInRequired("Sign in again to refresh this library.") from None
        raise ProviderError("The library service returned HTTP " + str(exc.code) + ". Try refreshing later.") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("The library service could not be reached. The previous library is retained.") from None
    if len(raw) > limit:
        raise ProviderError("The provider response exceeded the supported size.")
    return raw


def json_request(url, **kwargs):
    try:
        return json.loads(request(url, **kwargs))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ProviderError("The library service returned an unreadable response.") from None


def cookie_header(cookies, host):
    output = []
    if not isinstance(cookies, (list, tuple)):
        return ""
    for item in cookies[:150]:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain", "")).lstrip(".").casefold()
        name, value = item.get("name"), item.get("value")
        if ("." in domain and (host == domain or host.endswith("." + domain))
                and isinstance(name, str) and isinstance(value, str)
                and len(name) < 200 and len(value) < 16000
                and not any(c in name + value for c in "\r\n;\0")):
            output.append(name + "=" + value)
    return "; ".join(output)
