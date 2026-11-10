"""Conservative TMDb movie/TV search adapter. Never alters media files.

Search results are candidates, not established identifications.
"""
import re
from urllib.parse import urlencode

from app.tmdb_languages import _request, ProviderUnavailable

KINDS = {"movies": "movie", "animation": "movie", "series": "tv", "anime": "tv"}


def query_candidates(title: str, kind: str, year: int | None = None, page: int = 1) -> list[dict]:
    """Return unverified, source-attributed choices from TMDb."""
    title = title.strip()
    if not title or len(title) > 200:
        raise ValueError("Search title must be 1-200 characters")
    if kind not in KINDS:
        raise ValueError("Choose a movie or TV library category")
    if type(page) is not int or not 1 <= page <= 5:
        raise ValueError("Page must be between 1 and 5")
    if year is not None and (type(year) is not int or not 1870 <= year <= 2100):
        raise ValueError("Invalid release year")
    media_type = KINDS[kind]
    params = {"query": title, "page": page, "include_adult": "false"}
    if year is not None:
        params["year" if media_type == "movie" else "first_air_date_year"] = year
    data = _request("/search/" + media_type + "?" + urlencode(params))
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ProviderUnavailable("Unexpected TMDb search response")
    matches = []
    for item in data["results"]:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            continue
        # Search results may contain localized display titles. Preserve the
        # original field separately and NEVER claim it is a confirmed match.
        orig = item.get("original_title" if media_type == "movie" else "original_name")
        display = item.get("title" if media_type == "movie" else "name")
        date = item.get("release_date" if media_type == "movie" else "first_air_date")
        poster = item.get("poster_path")
        if not isinstance(orig, str) or not orig.strip():
            continue
        if not isinstance(display, str):
            display = orig
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            date = None
        if not isinstance(poster, str) or not re.fullmatch(r"/[a-zA-Z0-9_-]+\.(?:jpg|png|webp)", poster):
            poster = None
        matches.append({
            "provider": "tmdb",
            "media_type": media_type,
            "provider_id": item["id"],
            "original_title": orig.strip(),
            "display_title": display.strip() or orig.strip(),
            "release_date": date,
            "poster_path": poster,
            "review_required": True,
        })
    return matches
