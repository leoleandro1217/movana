"""Stable, provider-scoped search cache keys; no credentials stored."""
import hashlib
import json


CACHE_TTL_HOURS = 24


def search_cache_key(title: str, kind: str, year: int | None, page: int) -> str:
    """Changes in provider or search options yield separate cached results."""
    payload = {
        "provider": "tmdb",
        "kind": kind,
        "title": title.strip().casefold(),
        "year": year,
        "page": page,
        "schema": 1,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
