# Metadata language preferences

**Status:** TMDb-only per-library preferences are implemented on the development branch. No automatic metadata enrichment or filename changes are performed in this phase.

## Behavior

Each library stores three independent options:

- `metadata_provider`: currently `tmdb`.
- `title_language`: `original` (default) or a TMDb-supported locale such as `fr-FR` or `en-US`.
- `title_fallback`: `original` (default; only supported policy for this phase).

The settings exist separately for every library, including multiple libraries of the same media type.

The language dropdown obtains locales directly from TMDb's **configuration/primary_translations** endpoint. The list is cached in process for 24 hours to avoid repeated requests. `original` is a locally supported option and requires no TMDb credential.

**Important distinction:** A locale listed by TMDb is a *supported option*, not proof that a particular movie or episode has that translation. At the per-title level Movana must accept a localized title only when that exact locale's translation record includes a nonempty title. Otherwise the genuine original title is returned. There is no generated or guessed translation. The helper in `app/tmdb_languages.py` enforces this behavior and is covered by offline tests.

Confirmed titles are kept separately from media filenames. The user explicitly selects a TMDb result in the tile's **Find on TMDb** dialog. The app then verifies that ID against TMDb and stores the identity in PostgreSQL. Each tile has a **Details** dialog: for a confirmed identity it fetches title translations, an overview, release date, genres and poster from TMDb, caching the sanitized response in PostgreSQL for 24 hours. A non-confirmed item shows local inventory only. Missing title translations use the actual original title; missing synopsis/art is explicitly labeled unavailable. Changing the language preference does **not** rename files or confirm a work.

## Setup

Set one of these optional environment variables in the Movana container:

- `TMDB_READ_ACCESS_TOKEN` (preferred bearer token), or
- `TMDB_API_KEY` (TMDb v3 API key).

Never commit tokens to GitHub. Without a credential, the language list API reports provider unavailable (503), and users can still select `original`. Saving an unsupported locale is rejected. If TMDb is unavailable and a language other than original is requested, Movana fails closed rather than relying on an invented set of locales.

## API

- `GET /api/providers/tmdb/languages` returns `original` plus fetched, verified TMDb locale codes.
- `POST /api/libraries` accepts `metadata_provider`, `title_language`, `title_fallback`.
- `PATCH /api/libraries/{id}/preferences` saves options on an existing library.
- `GET /api/libraries` returns these settings for each library.
- `GET /api/metadata/tmdb/search` lists candidate identities without accepting any match.
- `POST /api/media/{id}/identify` verifies and persists a manually selected TMDb ID.
- `GET /api/media/{id}/details` returns local inventory plus a cached, sanitized TMDb profile, when confirmed.

Other providers (OMDb, AniDB, TheTVDB) will be implemented as separate adapters, with their own language capabilities and fallback rules; they must not be presented as supported until functional.

## Security and resource usage

This early alpha has no built-in account authentication; do not expose the HTTP service to untrusted networks. Only an admin on a trusted network should change library preferences. TMDb requests use a finite timeout and a 24-hour in-memory locale cache. Language choices are validated server-side, not just in the browser.

TMDb API data and original titles remain attributed to TMDb under the provider's applicable terms.

## Limits of the current detail view

- No automatic catalog matching, and no file move, rename or torrent registration.
- File size and path come from the local inventory scan; video/audio codecs, tracks and languages have not been inspected with ffprobe and are labeled **not inspected**.
- Cross-seed state is labeled **not checked** until that feature has been safely integrated.
- With `title_language=original`, TMDb is asked for contextual synopsis metadata in `en-US`; this is not necessarily the synopsis's original language. It is not a generated translation.
- Posters use validated TMDb poster paths from the trusted TMDb image origin, shown only after opening a details dialog.

## On-demand technical media inspection

The **Inspect technical tracks (read-only)** button inside a media detail dialog runs `ffprobe` only for the explicitly selected, already indexed file. It lists real video codec and dimensions, audio codecs, audio languages and channel counts, subtitle codec/language, and duration where the container exposes them. Missing properties remain unknown; audio languages are not inferred from release names. The scan does **not** run during library scans or when opening a detail dialog.

- The Docker media mount stays `/media:ro` and the service runs as an unprivileged user.
- Only inventory paths confined to the mount are probed. Symlinks and files whose indexed size/mtime changed are rejected for review/rescan.
- `ffprobe` is bundled in the image (via the `ffmpeg` package), runs with a 25-second timeout and no shell, and output is bounded to 1 MB.
- The result is returned to the browser on demand; no media writes, torrent actions, or automatic bulk inspection are performed.
- The technical endpoint is `GET /api/media/{id}/technical`.
