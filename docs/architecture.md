# Movana — Architecture (proposed)

> **Status: design proposal, not implemented yet.** This document describes our target architecture for the first releases. Actual deployment and API behavior must be validated before enabling filesystem writes.

Movana is a self-hosted media library inventory and automation platform, designed for Docker-compatible NAS systems. The Windows MediaCleanarr client remains a separate project. Jellyfin and qBittorrent remain independent applications.

## Infrastructure and integrations

```mermaid
flowchart TB
    Browser["Web browser / mobile"]
    subgraph Compose["Movana — one Docker Compose project"]
        App["movana app container<br/>Web UI + FastAPI + modular workers"]
        DB[("PostgreSQL<br/>persistent volume")]
        App <-->|SQL + retries| DB
    end
    subgraph NAS["NAS media storage"]
        Incoming[("Downloads")]
        Library[("Media library")]
    end
    Qbit["qBittorrent API"]
    Jelly["Jellyfin"]
    Catalogs["TMDb / TheTVDB / anime metadata providers"]
    Indexer["Optional C411 / Torznab indexer"]

    Browser <--> App
    App <-->|read-only inventory initially| Incoming
    App <-->|read-only inventory initially| Library
    App <-->|torrent state, managed rename/move later| Qbit
    Qbit <--> Incoming
    Qbit <--> Library
    Jelly -->|normal library scan| Library
    App <-->|metadata lookup| Catalogs
    App <-->|candidate release lookup| Indexer
```

The **initial alpha mounts media read-only**. Filesystem mutations and qBittorrent-controlled moves are future, explicitly tested features. For torrent-managed content, prefer qBittorrent's own APIs for renaming and changing save locations; do not rename its files out-of-band.

## Internal modules

```mermaid
flowchart LR
    UI["Web UI"] --> API["HTTP API"]
    API --> Jobs["Persistent job scheduler"]
    Jobs --> Scan["Library scanner"]
    Jobs --> Meta["Metadata resolver"]
    Jobs --> Anime["Anime matching"]
    Jobs --> Probe["Media inspector / ffprobe"]
    Jobs --> Organize["File organizer"]
    Jobs --> Torrent["Torrent adapter"]
    Jobs --> Upgrade["Edition comparison advisor"]
    Scan --> DB[("PostgreSQL")]
    Meta --> DB
    Anime --> DB
    Probe --> DB
    Organize --> DB
    Torrent --> DB
    Upgrade --> DB
```

Each module has its own contract, tests, and error handling. Modules may share one process in the initial app container, but must remain separable later. The database is the authoritative record of identities and job state, **not** proof of the current location of a file until reconciled.

## Startup and outage recovery

```mermaid
flowchart TD
    Boot["Docker Compose starts"] --> DB["PostgreSQL starts"]
    DB --> Healthy{"DB healthcheck passes?"}
    Healthy -->|No| Retry["Wait and retry"]
    Retry --> Healthy
    Healthy -->|Yes| App["Movana launches"]
    App --> Connect["Connect to DB, verify schema, apply controlled migrations"]
    Connect --> Ready["Serve UI and schedule work"]
    Ready --> External["Check optional external integrations"]
    External -->|Unavailable| Degraded["Mark integration degraded; retry later"]
    External -->|Available| Active["Resume permitted jobs"]
    Degraded --> External
```

Compose `depends_on: condition: service_healthy` helps at initial startup only. Movana must **also** retry DB connections after restarts, report readiness separately from liveness, and treat qBittorrent, Jellyfin, metadata providers and C411 as optional integrations that never prevent the UI from starting. Database outage must suspend state-changing jobs.

## Download-complete processing (future phase)

```mermaid
flowchart TD
    Done["qBittorrent download complete"] --> Enqueue["Idempotent job keyed by torrent identity"]
    Enqueue --> Identify["Resolve media identity"]
    Identify --> Confidence{"Confident match?"}
    Confidence -->|No| Manual["Manual review, no move"]
    Confidence -->|Yes| Inspect["ffprobe tracks / verify files"]
    Inspect --> Plan["Plan destination and filename"]
    Plan --> Validate{"Safe and collision-free?"}
    Validate -->|No| Manual
    Validate -->|Yes| Dryrun["Record proposed operation / dry-run"]
    Dryrun --> Approved{"Automatic policy permits move?"}
    Approved -->|No| Manual
    Approved -->|Yes| Qbit["Use qBittorrent rename / location APIs"]
    Qbit --> Verify{"Reconcile actual paths and torrent state"}
    Verify -->|No| Stop["Suspend job and alert"]
    Verify -->|Yes| Commit["Commit verified inventory state"]
    Commit --> Jelly["Jellyfin sees content through its own scan"]
```

For multi-file torrents, paths may need per-file operations. Moves across filesystems may involve copying and a longer transition, and must not be treated as atomic. No content deletion or replacement without validation. A restart or duplicate event must never produce two relocations.

## Suggested persistent data model

- **MediaWork**: movie, series, anime and canonical provider IDs.
- **Edition**: an identifiable release/version of a work.
- **PhysicalFile**: path, size, timestamps, container and available checksums.
- **Track**: detected audio, subtitle and video properties (measured by ffprobe).
- **TorrentAssociation**: qBittorrent hash, file index, save path and observed state.
- **Job / OperationLog**: work state, idempotency key, attempted action, outcome and reconciliation evidence.
- **ReleaseCandidate**: external catalog/indexer suggestion, *unverified* until independently checked.

This prevents us from conflating a movie, a particular edition, a physical file and a torrent.

## Contribution and change boundaries

New providers should implement a documented adapter interface, return normalized results, respect rate limits and support unavailable-provider behavior. New operations must support dry-run, collision checks, durable audit logging, and explicit tests for failure/restart cases.

See [CONTRIBUTING.md](../CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md).