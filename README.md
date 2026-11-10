# Movana

**Your media. Organized. Evolved.**

Movana is an open-source, self-hosted media-library manager designed for Docker-compatible NAS and Linux systems.

> **Alpha 0.1 — first development preview.** Read-only media inventory, PostgreSQL persistence, basic title search and tiled web view. It is not yet tested on a real NAS. No TMDb posters, qBittorrent manipulation, C411 integrations or automatic moves are implemented in this release.

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

Press **Scan library**. The first scan inventories supported video extensions recursively, skipping symlinks and inaccessible files. Search and filter the resulting tiles. Poster artwork and true metadata identification are planned for later.

**Security:** Alpha 0.1 has no login system. Do not expose the HTTP port to the public Internet. Use local-only binding by default; LAN users must secure network access. Do not commit `.env` or include your media paths in bug reports. Database data is persisted in a named Docker volume; treat it as sensitive.

**Inventory behavior:** Scans add/update existing paths but do **not yet remove** entries for files missing on subsequent scans. Basic titles and types are heuristically inferred from names and directory structure. File contents are not opened or modified. Scan errors appear in the UI.

## Health endpoints
- `GET /health/live`: application process responding.
- `GET /health/ready`: PostgreSQL connection working.
- `GET /api/media`: paginated inventory search.
- `POST /api/scan`: asynchronous inventory scan (one at a time).
- `GET /api/status`: scan progress.

## Documentation
- [Architecture and Mermaid diagrams](docs/architecture.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)

MIT licensed.