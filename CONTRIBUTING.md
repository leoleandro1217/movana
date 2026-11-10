# Contributing to Movana

Welcome! Movana is intended for everyone who wants a self-hosted, transparent media library management system, not just one NAS model.

## Recommended workflow
1. Open an issue or discussion describing the need and intended behavior.
2. Fork the repository and create a focused branch, for example `feat/anime-numbering` or `fix/db-reconnect`.
3. Keep changes scoped to one module and include tests, especially for failure and restart cases.
4. Update the documentation and Mermaid diagrams when changing architecture or data flows.
5. Submit a pull request explaining the change, test steps, risks and affected storage operations.

## Safety and compatibility
- Never hard-code UGREEN, QNAP or Synology host paths. All mounts and secrets must be configurable.
- Initial inventory runs read-only. Proposed file operations must support dry-run and explicit guardrails.
- Do not silently overwrite, unlink or delete media.
- For qBittorrent-managed files use its API, check actual state after operations and preserve torrent associations.
- Treat provider/indexer search results as suggestions, not confirmed file contents.
- External providers must be optional: outages must not prevent basic inventory.
- Do not commit credentials, private tracker keys, or personal media inventories.

## Code organization (planned)
`app/api`, `app/modules/scanner`, `app/modules/metadata`, `app/modules/anime`, `app/modules/inspector`, `app/modules/organizer`, `app/modules/torrents`, `app/modules/upgrades`, `web`, `tests`, `docs`.

The exact layout will be established alongside the first implementation. See [architecture](docs/architecture.md) and [roadmap](docs/ROADMAP.md).

## License
Contributions are made under the repository's MIT license.