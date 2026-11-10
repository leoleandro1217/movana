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

Current library tiles continue to show filenames parsed during inventory, because TMDb work identification and retrieval of per-title translations are not implemented yet. Changing the language preference does **not** rename existing files or imply they have been identified.

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

Other providers (OMDb, AniDB, TheTVDB) will be implemented as separate adapters, with their own language capabilities and fallback rules; they must not be presented as supported until functional.

## Security and resource usage

This early alpha has no built-in account authentication; do not expose the HTTP service to untrusted networks. Only an admin on a trusted network should change library preferences. TMDb requests use a finite timeout and a 24-hour in-memory locale cache. Language choices are validated server-side, not just in the browser.

TMDb API data and original titles remain attributed to TMDb under the provider's applicable terms.
