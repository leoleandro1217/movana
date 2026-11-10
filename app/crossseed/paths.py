"""Explicit, offline NAS-to-torrent-client path mapping.

No filesystem access, network access or automatic path discovery.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class PathMap:
    movana_root: str
    client_root: str


def _absolute(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.startswith("/") or chr(0) in value or chr(92) in value:
        raise ValueError("Path must be an absolute POSIX path")
    if any(piece in ("", ".", "..") for piece in value[1:].split("/")):
        raise ValueError("Path contains unsafe or ambiguous components")
    path = PurePosixPath(value)
    if path == PurePosixPath("/"):
        raise ValueError("Root-only mappings are not permitted")
    return path


def translate_path(source: str, mappings: tuple[PathMap, ...]) -> str:
    """Choose the most specific configured mapping, reject collisions.

    Mapping a path is not proof qBittorrent can read it: a sandbox must
    validate both mounts and file identity before any torrent registration.
    """
    origin = _absolute(source)
    matches = []
    for mapping in mappings:
        left, right = _absolute(mapping.movana_root), _absolute(mapping.client_root)
        if origin == left or left in origin.parents:
            relative = origin.relative_to(left)
            matches.append((len(left.parts), right / relative))
    if not matches:
        raise ValueError("No NAS-to-client path mapping covers this file")
    matches.sort(key=lambda item: item[0], reverse=True)
    longest = matches[0][0]
    best = {path.as_posix() for length, path in matches if length == longest}
    if len(best) != 1:
        raise ValueError("Ambiguous path mappings")
    return best.pop()
