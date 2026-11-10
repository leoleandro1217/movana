"""Offline torrent manifest comparison. No filesystem or torrent-client access.

A plausible path/size mapping is NOT a binary match; it must never be used
to initiate seeding without independent torrent-piece verification.
"""
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class Coverage(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ManifestFile:
    path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Mapping:
    torrent_path: str
    local_path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class LayoutDecision:
    coverage: Coverage
    mappings: tuple[Mapping, ...]
    missing_torrent_paths: tuple[str, ...]
    reason: str
    verified: bool = False


def _check(files: tuple[ManifestFile, ...], side: str):
    seen = set()
    for item in files:
        if not isinstance(item, ManifestFile):
            raise ValueError(side + " entries must be ManifestFile")
        path = item.path
        if not isinstance(path, str) or not path or "\\x00" in path or "\\\\" in path:
            raise ValueError(side + " has an invalid path")
        p = PurePosixPath(path)
        # Reject traversal, absolute paths, and odd names before matching.
        if p.is_absolute() or any(part in ("", ".", "..") for part in path.split("/")):
            raise ValueError(side + " path is not safe and relative")
        if path in seen:
            raise ValueError(side + " has duplicate paths")
        seen.add(path)
        if isinstance(item.size_bytes, bool) or not isinstance(item.size_bytes, int) or item.size_bytes < 0:
            raise ValueError(side + " has an invalid file size")


def compare_layout(
    local_files: tuple[ManifestFile, ...],
    torrent_files: tuple[ManifestFile, ...],
) -> LayoutDecision:
    """Compare individual file sizes without choosing ambiguous mappings.

    Only unique exact-size matches are assigned. Matching paths can disambiguate
    same-size files, but an ambiguous candidate is NEVER marked full.
    No hashes are computed and verified is always False.
    """
    _check(local_files, "local")
    _check(torrent_files, "torrent")
    if not torrent_files:
        return LayoutDecision(Coverage.NONE, (), (), "Empty torrent manifest")

    remaining = {f.path: f for f in local_files}
    assignments = {}
    unresolved = []
    # First resolve identical relative paths with identical sizes.
    for remote in torrent_files:
        direct = remaining.get(remote.path)
        if direct is not None and direct.size_bytes == remote.size_bytes:
            assignments[remote.path] = direct.path
            del remaining[direct.path]
        else:
            unresolved.append(remote)
    # Next resolve only unique size occurrences on both sides.
    sizes = Counter(f.size_bytes for f in unresolved)
    local_by_size = {}
    for item in remaining.values():
        local_by_size.setdefault(item.size_bytes, []).append(item.path)
    ambiguous = []
    missing = []
    for remote in unresolved:
        alternatives = local_by_size.get(remote.size_bytes, [])
        if not alternatives:
            missing.append(remote.path)
        elif sizes[remote.size_bytes] == 1 and len(alternatives) == 1:
            assignments[remote.path] = alternatives.pop()
        else:
            ambiguous.append(remote.path)
    mappings = tuple(
        Mapping(f.path, assignments[f.path], f.size_bytes)
        for f in torrent_files if f.path in assignments
    )
    if ambiguous:
        return LayoutDecision(
            Coverage.AMBIGUOUS, mappings, tuple(missing + ambiguous),
            "Multiple mappings share a size; user review required"
        )
    if not mappings:
        return LayoutDecision(Coverage.NONE, (), tuple(missing), "No exact-size file matches")
    if missing:
        return LayoutDecision(
            Coverage.PARTIAL, mappings, tuple(missing),
            "Some torrent files have no local counterpart; inspection only"
        )
    return LayoutDecision(
        Coverage.FULL, mappings, (), "Every torrent file has a plausible size mapping; hash check required"
    )
