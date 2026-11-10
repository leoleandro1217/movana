"""User-defined library configuration with safe paths under the media mount."""
from pathlib import Path

TYPES = {"movies", "series", "anime", "animation", "mixed"}


def resolve_library_path(root: Path, supplied: str) -> tuple[str, Path]:
    """Return canonical root-relative folder and absolute path, excluding mount root."""
    if not supplied or "\x00" in supplied:
        raise ValueError("A library folder is required")
    root = root.resolve(strict=True)
    requested = Path(supplied)
    # Accept container absolute paths (/media/...) or root-relative paths.
    if requested.is_absolute():
        candidate = requested
    else:
        candidate = root / requested
    # Absolute paths outside the configured mount are never accepted.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError("Path must be inside the mounted media directory") from None
    # strict=True prevents missing paths; resolution also catches symlink escapes.
    actual = candidate.resolve(strict=True)
    if actual == root or root not in actual.parents:
        raise ValueError("Choose a subfolder inside the mounted media directory")
    if not actual.is_dir():
        raise ValueError("The selected folder is not a directory")
    # Do not follow symlinks in a library path, even if they point back under root.
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink paths are not supported")
    return actual.relative_to(root).as_posix(), actual


def conflicts(candidate: str, existing: list[str]) -> bool:
    """A file should be owned by only one library root."""
    new = Path(candidate)
    for saved in existing:
        old = Path(saved)
        if new == old or new in old.parents or old in new.parents:
            return True
    return False
