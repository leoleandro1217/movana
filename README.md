# Movana

**Intelligent, self-hosted media library management for Docker-compatible NAS systems.**

Movana is an open-source project for inventorying, identifying, organizing and improving movie, TV and anime libraries. The initial version is **under design**; no functional Docker release has been published yet.

### Project documentation

- [Infrastructure architecture and Mermaid diagrams](docs/architecture.md)
- [Development roadmap](docs/ROADMAP.md)
- [Contributing and branching guide](CONTRIBUTING.md)

### Design principles

- NAS-agnostic Docker deployment
- Read-only inventory first; controlled and auditable file operations later
- Modular metadata, anime matching, media inspection and torrent adapters
- Optional qBittorrent and C411 integrations, independent of Jellyfin
- Safe recovery after restarts and external-service outages

> **Status: planning / early development.** No automatic file moves or replacements are implemented yet.

MIT licensed. Contributions and design discussions welcome.
