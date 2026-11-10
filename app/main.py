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
            SELECT l.id, l.name, l.kind, l.folder, COUNT(f.id) AS file_count
            FROM libraries l LEFT JOIN media_files f ON f.library_id = l.id
            GROUP BY l.id ORDER BY l.id
        """).fetchall()
    return {"items": rows}


@app.post("/api/libraries", status_code=201)
def create_library(request: LibraryInput):
    name = request.name.strip()
    if not name or request.kind not in TYPES:
        raise HTTPException(status_code=422, detail="Invalid name or media type")
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
            INSERT INTO libraries (name, kind, folder) VALUES (%s, %s, %s)
            RETURNING id, name, kind, folder
        """, (name, request.kind, folder)).fetchone()
    return result


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
    criteria = ["title ILIKE %s ESCAPE '\\'"]
    args = ["%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
    if library_id is not None:
        criteria.append("library_id = %s")
        args.append(library_id)
    where = "WHERE " + " AND ".join(criteria)
    with connection() as conn:
        rows = conn.execute(
            f"SELECT id,relative_path,title,category,release_year,size_bytes,library_id FROM media_files {where} ORDER BY title,id LIMIT %s OFFSET %s",
            args + [limit, offset]).fetchall()
        total = conn.execute(f"SELECT count(*) AS count FROM media_files {where}", args).fetchone()["count"]
    return {"items": rows, "total": total, "limit": limit, "offset": offset}
