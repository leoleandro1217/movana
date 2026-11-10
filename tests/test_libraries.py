"""Fast tests for library validation (no NAS or database needed)."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DB_PASSWORD", "test-only")

from app.libraries import TYPES, conflicts, resolve_library_path


class LibrariesTests(unittest.TestCase):
    def test_common_types(self):
        self.assertTrue({"movies", "series", "anime", "animation", "mixed"} <= TYPES)

    def test_safe_relative_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Movies 4K").mkdir()
            rel, absolute = resolve_library_path(root, "Movies 4K")
            self.assertEqual(rel, "Movies 4K")
            self.assertEqual(absolute, root / "Movies 4K")

    def test_mount_root_cannot_be_a_library(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_library_path(Path(folder), ".")

    def test_outside_mount_not_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_library_path(Path(folder), "/etc")

    def test_overlap(self):
        self.assertTrue(conflicts("Films/4K", ["Films"]))
        self.assertTrue(conflicts("Films", ["Films/4K"]))
        self.assertFalse(conflicts("Films", ["Films 4K"]))
        self.assertFalse(conflicts("Films", ["Series"]))

    def test_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Real").mkdir()
            (root / "Link").symlink_to(root / "Real", target_is_directory=True)
            with self.assertRaises(ValueError):
                resolve_library_path(root, "Link")


if __name__ == "__main__":
    unittest.main()
