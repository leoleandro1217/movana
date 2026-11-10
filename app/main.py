"""Movana: lightweight, read-only media-library inventory alpha."""
import asyncio
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from app.libraries import TYPES, conflicts, resolve_library_path
from app.tmdb_languages import ProviderUnavailable, supported_locales, validate_preferences
from app.tmdb_search import query_candidates, fetch_identity
from app.search_cache import search_cache_key, CACHE_TTL_HOURS

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media")).resolve()
DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("DB_NAME", "movana")
DB_USER = os.environ.get("DB_USER", "movana")
DB_PASSWORD = os.environ["DB_PASSWORD"]
EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".ts", ".mpg", ".mpeg", ".webm"}
scan_lock = threading.Lock()
scan_state = {"running": False, "scanned": 0, "library_id": None, "error": None, "finished_at": None}


def connection():
    return psycopg.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                           connect_timeout=5, row_factory=dict_row)


def initialize_database():
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS libraries (
                id BIGSERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                kind VARCHAR(16) NOT NULL CHECK (kind IN ('movies','series','anime','animation','mixed')),
                folder TEXT NOT NULL UNIQUE,
                metadata_provider TEXT NOT NULL DEFAULT 'tmdb',
                title_language TEXT NOT NULL DEFAULT 'original',
                title_fallback TEXT NOT NULL DEFAULT 'original',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_files (
                id BIGSERIAL PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                release_year INTEGER,
                size_bytes BIGINT NOT NULL,
                modified_ns BIGINT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                library_id BIGINT REFERENCES libraries(id)
            )
        """)
        # In-place additive upgrade from the first alpha.
        conn.execute("ALTER TABLE media_files ADD COLUMN IF NOT EXISTS library_id BIGINT REFERENCES libraries(id)")
        conn.execute("ALTER TABLE libraries ADD COLUMN IF NOT EXISTS metadata_provider TEXT NOT NULL DEFAULT 'tmdb'")
        conn.execute("ALTER TABLE libraries ADD COLUMN IF NOT EXISTS title_language TEXT NOT NULL DEFAULT 'original'")
        conn.execute("ALTER TABLE libraries ADD COLUMN IF NOT EXISTS title_fallback TEXT NOT NULL DEFAULT 'original'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata_search_cache (
                cache_key CHAR(64) PRIMARY KEY,
                results JSONB NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                cached_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_identifications (
                media_file_id BIGINT PRIMARY KEY REFERENCES media_files(id) ON DELETE CASCADE,
                provider TEXT NOT NULL CHECK (provider = 'tmdb'),
                media_type TEXT NOT NULL CHECK (media_type IN ('movie','tv')),
                provider_id INTEGER NOT NULL,
                original_title TEXT NOT NULL,
                confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_media_title ON media_files (lower(title))")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_media_library ON media_files (library_id)")


def parse_name(path: Path):
    name = re.sub(r"[._]+", " ", path.stem)
    name = re.sub(r"(?i)\b(2160p|1080p|720p|bluray|web-dl|webrip|x264|x265|h264|h265|hevc)\b.*$", "", name)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", name)
    episode = re.search(r"(?i)\bS\d{1,2}E\d{1,3}\b", name)
    if episode:
        name = name[:episode.start()]
    elif year:
        name = name[:year.start()]
    title = re.sub(r"\s+", " ", name).strip(" -._") or path.stem
    parts = {p.lower() for p in path.parts}
    kind = "anime" if {"anime", "animes", "animés"} & parts else ("series" if episode or {"series", "tv", "shows"} & parts else "movies")
    return title, kind, int(year.group(1)) if year else None


def store_batch(conn, batch):
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO media_files (relative_path, title, category, release_year, size_bytes, modified_ns, library_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (relative_path) DO UPDATE SET
                title = excluded.title, category = excluded.category,
                release_year = excluded.release_year, size_bytes = excluded.size_bytes,
                modified_ns = excluded.modified_ns, library_id = excluded.library_id,
                observed_at = now()
        """, batch)
    conn.commit()


def inventory_scan(library_id, folder, kind):
    count, error = 0, None
    try:
        # Revalidate stored paths against the mount on every scan.
        _, library_path = resolve_library_path(MEDIA_ROOT, folder)
        with connection() as conn:
            batch = []
            for base, directories, filenames in os.walk(library_path, followlinks=False):
                directories[:] = [d for d in directories if not (Path(base) / d).is_symlink()]
                for filename in filenames:
                    filepath = Path(base) / filename
                    if filepath.suffix.lower() not in EXTENSIONS or filepath.is_symlink():
                        continue
                    try:
                        stat = filepath.stat()
                    except OSError:
                        continue
                    rel = filepath.relative_to(MEDIA_ROOT).as_posix()
                    title, guessed_kind, year = parse_name(Path(rel))
                    category = kind if kind != "mixed" else guessed_kind
                    batch.append((rel, title, category, year, stat.st_size, stat.st_mtime_ns, library_id))
                    count += 1
                    if len(batch) >= 250:
                        store_batch(conn, batch)
                        batch.clear()
                        with scan_lock:
                            scan_state["scanned"] = count
            if batch:
                store_batch(conn, batch)
    except Exception as exc:
        error = str(exc)
    finally:
        with scan_lock:
            scan_state.update(running=False, scanned=count, error=error, finished_at=int(time.time()))


class LibraryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = "movies"
    folder: str = Field(min_length=1, max_length=2000)
    metadata_provider: str = "tmdb"
    title_language: str = "original"
    title_fallback: str = "original"


class LibraryPreferences(BaseModel):
    metadata_provider: str = "tmdb"
    title_language: str = "original"
    title_fallback: str = "original"


def check_preferences(provider: str, language: str, fallback: str):
    try:
        validate_preferences(provider, language, fallback)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



@asynccontextmanager
async def lifespan(app):
    for attempt in range(30):
        try:
            await asyncio.to_thread(initialize_database)
            break
        except psycopg.OperationalError:
            if attempt == 29:
                raise
            await asyncio.sleep(2)
    yield


app = FastAPI(title="Movana", version="0.1.1-alpha", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def home():
    return (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="database unavailable")


@app.get("/api/status")
def status():
    with scan_lock:
        return dict(scan_state)


@app.get("/api/libraries")
def libraries():
    with connection() as conn:
        rows = conn.execute("""
            SELECT l.id, l.name, l.kind, l.folder, l.metadata_provider, l.title_language, l.title_fallback, COUNT(f.id) AS file_count
            FROM libraries l LEFT JOIN media_files f ON f.library_id = l.id
            GROUP BY l.id ORDER BY l.id
        """).fetchall()
    return {"items": rows}


@app.post("/api/libraries", status_code=201)
def create_library(request: LibraryInput):
    name = request.name.strip()
    if not name or request.kind not in TYPES:
        raise HTTPException(status_code=422, detail="Invalid name or media type")
    check_preferences(request.metadata_provider, request.title_language, request.title_fallback)
    try:
        folder, _ = resolve_library_path(MEDIA_ROOT, request.folder)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    with connection() as conn:
        # Serialize concurrent library additions, including cross-process requests.
        conn.execute("SELECT pg_advisory_xact_lock(744182)")
        existing = [row["folder"] for row in conn.execute("SELECT folder FROM libraries").fetchall()]
        if conflicts(folder, existing):
            raise HTTPException(status_code=409, detail="Library folders must not overlap")
        result = conn.execute("""
            INSERT INTO libraries (name, kind, folder, metadata_provider, title_language, title_fallback)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, name, kind, folder, metadata_provider, title_language, title_fallback
        """, (name, request.kind, folder, request.metadata_provider, request.title_language, request.title_fallback)).fetchone()
    return result


@app.get("/api/providers/tmdb/languages")
def tmdb_languages():
    try:
        locales = supported_locales()
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"provider": "tmdb", "languages": ["original"] + locales}


@app.patch("/api/libraries/{library_id}/preferences")
def update_library_preferences(library_id: int, request: LibraryPreferences):
    check_preferences(request.metadata_provider, request.title_language, request.title_fallback)
    with connection() as conn:
        row = conn.execute("""
            UPDATE libraries SET metadata_provider = %s, title_language = %s, title_fallback = %s
            WHERE id = %s
            RETURNING id, metadata_provider, title_language, title_fallback
        """, (request.metadata_provider, request.title_language, request.title_fallback, library_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return row


@app.get("/api/metadata/tmdb/search")
def metadata_search(title: str, kind: str, year: int | None = None, page: int = 1):
    """Manual, non-mutating metadata candidate lookup; never accepts a file path."""
    # Validate arguments before touching the cache, even for cached queries.
    title = title.strip()
    if not title or len(title) > 200 or kind not in ("movies", "animation", "series", "anime") or not 1 <= page <= 5:
        raise HTTPException(status_code=422, detail="Invalid search title, kind or page")
    if year is not None and not 1870 <= year <= 2100:
        raise HTTPException(status_code=422, detail="Invalid release year")
    key = search_cache_key(title, kind, year, page)
    with connection() as conn:
        hit = conn.execute("""
            SELECT results FROM metadata_search_cache
            WHERE cache_key = %s AND expires_at > now()
        """, (key,)).fetchone()
    if hit is not None:
        return {"items": hit["results"], "review_required": True, "cached": True}
    try:
        items = query_candidates(title=title, kind=kind, year=year, page=page)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    from psycopg.types.json import Jsonb
    with connection() as conn:
        conn.execute("""
            INSERT INTO metadata_search_cache (cache_key, results, expires_at)
            VALUES (%s, %s, now() + (%s * interval '1 hour'))
            ON CONFLICT (cache_key) DO UPDATE SET
                results = EXCLUDED.results, expires_at = EXCLUDED.expires_at, cached_at = now()
        """, (key, Jsonb(items), CACHE_TTL_HOURS))
    return {"items": items, "review_required": True, "cached": False}


class ManualIdentityChoice(BaseModel):
    provider_id: int = Field(gt=0)


@app.post("/api/media/{media_id}/identify")
def confirm_identity(media_id: int, request: ManualIdentityChoice):
    """Explicit user confirmation only; writes DB metadata, never media files."""
    with connection() as conn:
        media = conn.execute(
            "SELECT id, category FROM media_files WHERE id = %s", (media_id,)
        ).fetchone()
    if media is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    category = media["category"]
    media_type = {"movies": "movie", "animation": "movie", "series": "tv"}.get(category)
    if media_type is None:
        raise HTTPException(status_code=422, detail="TMDb identification not enabled for this category")
    try:
        match = fetch_identity(media_type, request.provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    with connection() as conn:
        result = conn.execute("""
            INSERT INTO media_identifications (media_file_id, provider, media_type, provider_id, original_title)
            SELECT id, 'tmdb', %s, %s, %s FROM media_files WHERE id = %s AND category = %s
            ON CONFLICT (media_file_id) DO UPDATE SET
                provider = EXCLUDED.provider, media_type = EXCLUDED.media_type,
                provider_id = EXCLUDED.provider_id, original_title = EXCLUDED.original_title,
                confirmed_at = now()
            RETURNING media_file_id, provider, media_type, provider_id, original_title
        """, (media_type, request.provider_id, match["original_title"], media_id, category)).fetchone()
    if result is None:
        raise HTTPException(status_code=409, detail="Media disappeared or changed category")
    return {"identification": result, "files_modified": False}


@app.post("/api/libraries/{library_id}/scan", status_code=202)
async def scan_library(library_id: int):
    with scan_lock:
        if scan_state["running"]:
            raise HTTPException(status_code=409, detail="Another scan is running")
        with connection() as conn:
            library = conn.execute("SELECT id, folder, kind FROM libraries WHERE id = %s", (library_id,)).fetchone()
        if library is None:
            raise HTTPException(status_code=404, detail="Library not found")
        scan_state.update(running=True, scanned=0, error=None, library_id=library_id, finished_at=None)
    asyncio.create_task(asyncio.to_thread(inventory_scan, library_id, library["folder"], library["kind"]))
    return {"status": "started", "library_id": library_id}


@app.post("/api/scan", status_code=202)
async def scan_all():
    raise HTTPException(status_code=400, detail="Choose a library to scan from the sidebar")


@app.get("/api/media")
def media(query: str = "", library_id: int | None = None, limit: int = 72, offset: int = 0):
    limit, offset = min(max(limit, 1), 200), max(offset, 0)
    criteria = ["m.title ILIKE %s ESCAPE '\\'"]
    args = ["%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
    if library_id is not None:
        criteria.append("m.library_id = %s")
        args.append(library_id)
    where = "WHERE " + " AND ".join(criteria)
    with connection() as conn:
        rows = conn.execute(
            f"SELECT m.id,m.relative_path,m.title,m.category,m.release_year,m.size_bytes,m.library_id,\n                   i.provider_id AS confirmed_tmdb_id, i.original_title AS confirmed_original_title\n            FROM media_files m LEFT JOIN media_identifications i ON i.media_file_id = m.id {where} ORDER BY m.title,m.id LIMIT %s OFFSET %s",
            args + [limit, offset]).fetchall()
        total = conn.execute(f"SELECT count(*) AS count FROM media_files m {where}", args).fetchone()["count"]
    return {"items": rows, "total": total, "limit": limit, "offset": offset}
