"""On-demand, read-only ffprobe inspection with bounded execution.

No media mutations, no automatic background processing and no invented tracks.
The caller must supply a validated, existing local media file.
"""
import json
import subprocess
from pathlib import Path

MAX_STREAMS = 96
MAX_OUTPUT_BYTES = 1_000_000
PROBE_TIMEOUT_SECONDS = 25


class ProbeError(Exception):
    """Probe unavailable, failed, timed out, or returned invalid data."""


def _language(tags):
    if not isinstance(tags, dict):
        return None
    value = tags.get("language") or tags.get("LANGUAGE")
    return value.strip()[:32] if isinstance(value, str) and value.strip() else None


def parse_probe(payload: dict) -> dict:
    """Parse explicit stream properties; unknown is None, not a guess."""
    if not isinstance(payload, dict) or not isinstance(payload.get("streams", []), list):
        raise ProbeError("Unexpected ffprobe result")
    result = {"video": [], "audio": [], "subtitles": [], "duration_seconds": None}
    fmt = payload.get("format") or {}
    if isinstance(fmt, dict):
        try:
            duration = float(fmt.get("duration"))
            if 0 <= duration < 10_000_000:
                result["duration_seconds"] = round(duration, 3)
        except (TypeError, ValueError, OverflowError):
            pass
    for stream in payload.get("streams", [])[:MAX_STREAMS]:
        if not isinstance(stream, dict):
            continue
        category = {"video": "video", "audio": "audio", "subtitle": "subtitles"}.get(stream.get("codec_type"))
        if not category:
            continue
        codec = stream.get("codec_name")
        details = {
            "index": stream.get("index") if type(stream.get("index")) is int else None,
            "codec": codec if isinstance(codec, str) and len(codec) <= 64 else None,
            "language": _language(stream.get("tags")),
        }
        if category == "video":
            for key in ("width", "height"):
                val = stream.get(key)
                details[key] = val if type(val) is int and 0 < val <= 65536 else None
        if category == "audio":
            channels = stream.get("channels")
            details["channels"] = channels if type(channels) is int and 0 < channels <= 64 else None
        result[category].append(details)
    return result


def inspect_file(path: Path) -> dict:
    """Read selected media file using ffprobe, never call any writer."""
    if not path.is_file() or path.is_symlink():
        raise ProbeError("Media file is missing or is a symlink")
    command = [
        "ffprobe", "-nostdin", "-v", "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height,channels:stream_tags=language",
        "-of", "json", str(path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("ffprobe unavailable or timed out") from exc
    if completed.returncode != 0:
        raise ProbeError("ffprobe could not inspect this file")
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise ProbeError("ffprobe output exceeds safety limit")
    try:
        return parse_probe(json.loads(completed.stdout))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError("Invalid ffprobe output") from exc
