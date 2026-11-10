"""TMDb title-language preferences and strict, source-backed title selection.

This module does not identify films or rename media files. Supported locales are
read from TMDb and cached; individual titles must be present in a TMDb
translation payload before they can be displayed.
"""
import json
import os
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TMDB_API = "https://api.themoviedb.org/3"
CACHE_SECONDS = 86400
_lock = threading.Lock()
_locale_cache = (0.0, [])


class ProviderUnavailable(Exception):
    pass


def _request(endpoint: str):
    token = os.environ.get("TMDB_READ_ACCESS_TOKEN", "").strip()
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not token and not key:
        raise ProviderUnavailable("Configure TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY")
    url = TMDB_API + endpoint
    if key and not token:
        url += ("&" if "?" in url else "?") + "api_key=" + key
    headers = {"Accept": "application/json", "User-Agent": "Movana/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=7) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ProviderUnavailable("TMDb configuration request failed") from exc


def supported_locales():
    """Fetch real supported TMDb website locales; never use a guessed list."""
    global _locale_cache
    with _lock:
        stamp, locales = _locale_cache
        if locales and time.monotonic() - stamp < CACHE_SECONDS:
            return list(locales)
        raw = _request("/configuration/primary_translations")
        if not isinstance(raw, list):
            raise ProviderUnavailable("Unexpected TMDb response")
        verified = sorted({
            item for item in raw
            if isinstance(item, str) and re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", item)
        })
        if not verified:
            raise ProviderUnavailable("TMDb returned no supported locales")
        _locale_cache = (time.monotonic(), verified)
        return list(verified)


def validate_preferences(provider: str, language: str, fallback: str):
    if provider != "tmdb":
        raise ValueError("Only TMDb is implemented in this phase")
    if fallback != "original":
        raise ValueError("Only original-title fallback is implemented")
    if language == "original":
        return
    if language not in supported_locales():
        raise ValueError("Language is not listed by TMDb")


def select_title(original_title: str | None, translations: list[dict], language: str):
    """Select exact locale translation or return original; never invent text.

    Translation records must include iso_639_1, iso_3166_1 and data.title
    (movies) or data.name (TV). This is deliberately not a filename parser.
    """
    original = (original_title or "").strip()
    if language == "original":
        return original or None
    if not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", language):
        raise ValueError("Invalid locale")
    lang, region = language.split("-", 1)
    for entry in translations:
        if not isinstance(entry, dict):
            continue
        if entry.get("iso_639_1") != lang or entry.get("iso_3166_1") != region:
            continue
        data = entry.get("data") or {}
        if not isinstance(data, dict):
            continue
        value = data.get("title") or data.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return original or None
