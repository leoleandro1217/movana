"""Verified TMDb profiles for manually confirmed media; read-only network requests.

TMDb data is never written to media files, and the profile response is never
used to infer a local codec, resolution, or language track.
"""
import re
from urllib.parse import urlencode

from app.tmdb_languages import _request, ProviderUnavailable, select_title

POSTER_RE = re.compile(r"/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)\Z")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def sanitize_profile(media_type: str, provider_id: int, payload: dict, language: str) -> dict:
    """Accept only TMDb-backed fields and the exact requested identity."""
    if media_type not in ("movie", "tv") or type(provider_id) is not int or provider_id <= 0:
        raise ValueError("Invalid identity")
    if not isinstance(payload, dict) or payload.get("id") != provider_id:
        raise ProviderUnavailable("TMDb profile identity mismatch")
    original_key = "original_title" if media_type == "movie" else "original_name"
    original = payload.get(original_key)
    if not isinstance(original, str) or not original.strip():
        raise ProviderUnavailable("TMDb has no original title for this entry")
    raw_translations = payload.get("translations") or {}
    translations = raw_translations.get("translations", []) if isinstance(raw_translations, dict) else []
    if not isinstance(translations, list):
        translations = []
    title = select_title(original, translations, language)
    date = payload.get("release_date" if media_type == "movie" else "first_air_date")
    if not isinstance(date, str) or not DATE_RE.fullmatch(date):
        date = None
    poster = payload.get("poster_path")
    if not isinstance(poster, str) or not POSTER_RE.fullmatch(poster):
        poster = None
    overview = payload.get("overview")
    if not isinstance(overview, str) or not overview.strip():
        overview = None
    else:
        overview = overview.strip()[:5000]
    genres = payload.get("genres", [])
    genre_names = []
    if isinstance(genres, list):
        for item in genres[:15]:
            name = item.get("name") if isinstance(item, dict) else None
            if isinstance(name, str) and name.strip():
                genre_names.append(name.strip()[:80])
    return {
        "provider": "tmdb",
        "provider_id": provider_id,
        "media_type": media_type,
        "original_title": original.strip(),
        "title": title,
        "title_language": language,
        "release_date": date,
        "overview": overview,
        "overview_language": language if language != "original" else "en-US",
        "poster_path": poster,
        "genres": genre_names,
    }


def fetch_profile(media_type: str, provider_id: int, language: str) -> dict:
    """Fetch TMDb work detail; translated title falls back to original.

    TMDb's original option has no corresponding overview locale; request
    en-US for contextual metadata and label it explicitly.
    """
    if media_type not in ("movie", "tv") or type(provider_id) is not int or provider_id <= 0:
        raise ValueError("Invalid identity")
    if language != "original" and not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", language):
        raise ValueError("Invalid title locale")
    params = urlencode({"language": "en-US" if language == "original" else language,
                        "append_to_response": "translations"})
    payload = _request("/" + media_type + "/" + str(provider_id) + "?" + params)
    return sanitize_profile(media_type, provider_id, payload, language)
