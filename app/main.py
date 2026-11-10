"""Movana Alpha 0.1: read-only filesystem inventory and tile UI."""
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
from psycopg.rows import dict_row

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media")).resolve()
DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("DB_NAME", "movana")
DB_USER = os.environ.get("DB_USER", "movana")
DB_PASSWORD = os.environ["DB_PASSWORD"]
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".ts", ".mpg", ".mpeg", ".webm"}
state_lock = threading.Lock()
scan_state = {"running": False, "scanned": 0, "error": None, "finished_at": None}


def connection():
    return psycopg.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, connect_timeout=5, row_factory=dict_row)


def initialize_database():
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_files (
                id BIGSERIAL PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                release_year INTEGER,
                size_bytes BIGINT NOT NULL,
                modified_ns BIGINT NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_media_title ON media_files (lower(title))")


def parse_name(path: Path):
    text = re.sub(r"[._]+", " ", path.stem)
    text = re.sub(r"(?i)\b(2160p|1080p|720p|bluray|web-dl|webrip|x264|x265|h264|h265|hevc)\b.*$", "", text)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    episode = re.search(r"(?i)\bS\d{1,2}E\d{1,3}\b", text)
    if episode:
        text = text[:episode.start()]
    elif year:
        text = text[:year.start()]
    title = re.sub(r"\s+", " ", text).strip(" -._") or path.stem
    parts = {p.lower() for p in path.parts}
    category = "anime" if {"anime", "animes", "animés"} & parts else ("series" if episode or {"series", "tv", "shows"} & parts else "movies")
    return title, category, int(year.group(1)) if year else None


def inventory_scan():
    count = 0
    error = None
    try:
        if not MEDIA_ROOT.is_dir():
            raise RuntimeError("Media root is not a mounted directory")
        with connection() as conn:
            batch = []
            for base, directories, filenames in os.walk(MEDIA_ROOT, followlinks=False):
                directories[:] = [d for d in directories if not (Path(base) / d).is_symlink()]
                for filename in filenames:
                    filepath = Path(base) / filename
                    if filepath.suffix.lower() not in VIDEO_EXTENSIONS or filepath.is_symlink():
                        continue
                    try:
                        stat = filepath.stat()
                    except OSError:
                        continue
                    rel = filepath.relative_to(MEDIA_ROOT).as_posix()
                    title, category, year = parse_name(Path(rel))
                    batch.append((rel, title, category, year, stat.st_size, stat.st_mtime_ns))
                    count += 1
                    if len(batch) >= 250:
                        store_batch(conn, batch)
                        batch.clear()
                        with state_lock:
                            scan_state["scanned"] = count
            if batch:
                store_batch(conn, batch)
    except Exception as exc:
        error = str(exc)
    finally:
        with state_lock:
            scan_state.update(running=False, scanned=count, error=error, finished_at=int(time.time()))


def store_batch(conn, batch):
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO media_files (relative_path, title, category, release_year, size_bytes, modified_ns)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (relative_path) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                release_year = excluded.release_year,
                size_bytes = excluded.size_bytes,
                modified_ns = excluded.modified_ns,
                observed_at = now()
        """, batch)
    conn.commit()


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


app = FastAPI(title="Movana", version="0.1.0-alpha", lifespan=lifespan)


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
    with state_lock:
        return dict(scan_state)


@app.post("/api/scan", status_code=202)
async def scan():
    with state_lock:
        if scan_state["running"]:
            raise HTTPException(status_code=409, detail="scan already running")
        scan_state.update(running=True, scanned=0, error=None)
    asyncio.create_task(asyncio.to_thread(inventory_scan))
    return {"status": "started"}


@app.get("/api/media")
def media(query: str = "", category: str = "all", limit: int = 72, offset: int = 0):
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    if category not in {"all", "movies", "series", "anime"}:
        raise HTTPException(status_code=400, detail="invalid category")
    where = "WHERE title ILIKE %s" + (" AND category = %s" if category != "all" else "")
    args = ["%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
    if category != "all":
        args.append(category)
    with connection() as conn:
        rows = conn.execute(
            f"SELECT id,relative_path,title,category,release_year,size_bytes FROM media_files {where} ORDER BY title LIMIT %s OFFSET %s",
            args + [limit, offset],
        ).fetchall()
        total = conn.execute(f"SELECT count(*) AS count FROM media_files {where}", args).fetchone()["count"]
    return {"items": rows, "total": total, "limit": limit, "offset": offset}
