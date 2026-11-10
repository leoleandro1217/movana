# Movana

**Your media. Organized. Evolved.**

Movana is an open-source, self-hosted media-library manager designed for Docker-compatible NAS and Linux systems.

> **Alpha 0.1 development preview.** Custom read-only media libraries, PostgreSQL persistence, per-library scanning, basic title search and tiled web view. It is not yet tested on a real NAS. No TMDb posters, qBittorrent manipulation, C411 integrations or automatic moves are implemented in this release. An isolated, non-networked cross-seed size prefilter is present for future integration.

## Quick start

Requires Docker Engine + Docker Compose v2. Run these commands on your NAS or a Linux Docker host.

```sh
git clone https://github.com/leoleandro1217/movana.git
cd movana
cp .env.example .env
```

Edit `.env` and provide:
- `DB_PASSWORD`: unique strong password for your PostgreSQL instance.
- `MEDIA_PATH`: absolute host directory containing your videos (mounted as `/media:ro`).
- `MOVANA_BIND_IP`: default `127.0.0.1` for local-only access; set to the NAS LAN IP if you need access from another machine, **but only on a trusted network**.
- `MOVANA_PORT`: defaults to `8088`.

Then start:

```sh
docker compose up -d --build
docker compose ps
```

Open `http://127.0.0.1:8088` if running locally, or `http://NAS-LAN-IP:8088` if you configured the LAN bind IP.

In the web interface, choose **Add library**, enter its name, category and a pre-existing folder under the mounted /media root. You can create multiple libraries of the same category (for example Movies and Movies 4K), each with a different folder. Select a library in the sidebar and press **Scan selected library**. Scans recurse through supported videos, skip symlinks and inaccessible files, and update PostgreSQL. Browse tiles per library or across all libraries. Library folders cannot overlap, to avoid ambiguous ownership. Poster artwork and true metadata identification are planned for later.

**Security:** Alpha 0.1 has no login system. Do not expose the HTTP port to the public Internet. Use local-only binding by default; LAN users must secure network access. Do not commit `.env` or include your media paths in bug reports. Database data is persisted in a named Docker volume; treat it as sensitive.

**Inventory behavior:** Scans add/update existing paths but do **not yet remove** entries for files missing on subsequent scans. This alpha supports one folder per named library; multi-folder libraries, editing/deleting libraries and automated routing are planned. Existing records created by the earlier single-root alpha remain unassigned until reindexed. Basic titles and types are heuristically inferred from names and directory structure. File contents are not opened or modified. Scan errors appear in the UI.

## Health endpoints
- `GET /health/live`: application process responding.
- `GET /health/ready`: PostgreSQL connection working.
- `GET /api/libraries`: configured libraries and counts.\n- `POST /api/libraries`: create named library with safe folder.\n- `POST /api/libraries/{id}/scan`: scan one library.\n- `GET /api/media`: paginated inventory search, optionally filtered by library_id.
- `POST /api/scan`: deprecated; select a library instead.
- `GET /api/status`: scan progress.

## Documentation
- [Architecture and Mermaid diagrams](docs/architecture.md)
- [Roadmap](docs/ROADMAP.md)
- [Cross-seed: architecture and safety](docs/CROSS_SEED.md)
- [Contributing](CONTRIBUTING.md)

MIT licensed.