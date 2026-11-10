# Movana roadmap

> Planned milestones, not claims of implemented functionality.

## Alpha 0.1 — Safe foundations
- Docker Compose: Movana app + PostgreSQL; DB healthchecks, connection retries
- API, bilingual web UI and tiled library view
- Read-only indexed media inventory and basic search
- Persist identities, filesystem paths, job states and scan history
- Test fixtures for films, series and anime

## Alpha 0.2 — Identification and inspection
- TMDb and TheTVDB metadata adapters, metadata cache
- Anime numbering strategies (season-based and absolute, including ambiguous cases)
- ffprobe video/audio/subtitle inventory
- Review queue for uncertain matches

## Alpha 0.3 — Controlled automation
- qBittorrent connection and completion detection
- Dry-run rename/move planning, collision protection
- qBittorrent-managed rename and location changes for supported cases
- Durable jobs, reconciliation and restart tests
- Deliberate testing of multi-file torrents and cross-volume moves

## Alpha 0.4 — Edition comparison
- Optional C411 / Torznab search adapter
- Audio-language and quality preferences
- Candidate alternative editions shown on library tiles
- Manual compare and review flow; never infer actual tracks from release names alone

## Out of scope for these milestones
- Ebook/ISBN management (possible later)
- Automatic destructive replacement
- Download acquisition or copying of protected releases
- Jellyfin replacement (Jellyfin manages its own library scan)

All milestones remain subject to testing and community review.

## Planned module — Existing media cross-seeding (after safe inventory and torrent adapter)

- Search an already indexed NAS library for candidate releases on a configured C411 / Torznab indexer.
- Reuse lessons and optional cross-seed integration from `c411-library-checker`; do not duplicate a mature verification engine.
- Match the torrent payload through file structure, sizes and piece-hash verification, never by title alone.
- Safely map renamed files to torrent paths; prevent duplicate torrent registration.
- Start with a dry-run and manual approval, then optional opt-in automation only for verified candidates.
- Never initiate unwanted re-downloads; log and stop on a mismatch.
- Respect tracker-specific rules, rate limits, and sharing permissions.
- Make cross-seeding optional: no dependency for normal library scans or UI operation.
