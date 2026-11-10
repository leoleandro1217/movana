"""Strict path mapping tests without qBittorrent or NAS."""
import unittest

from app.crossseed.paths import PathMap, translate_path


class MappingTests(unittest.TestCase):
    def test_nested_path(self):
        self.assertEqual(
            translate_path("/media/Films/Alien.mkv", (PathMap("/media", "/mnt/storage"),)),
            "/mnt/storage/Films/Alien.mkv"
        )

    def test_most_specific_mapping_wins(self):
        pairs = (PathMap("/media", "/data"), PathMap("/media/Films", "/special"))
        self.assertEqual(translate_path("/media/Films/Alien.mkv", pairs), "/special/Alien.mkv")

    def test_boundary_is_respected(self):
        with self.assertRaises(ValueError):
            translate_path("/media2/movie.mkv", (PathMap("/media", "/data"),))

    def test_same_priority_conflict_fails(self):
        with self.assertRaises(ValueError):
            translate_path("/media/movie.mkv", (
                PathMap("/media", "/one"), PathMap("/media", "/two")
            ))

    def test_unmapped_fails(self):
        with self.assertRaises(ValueError):
            translate_path("/unknown/test", (PathMap("/media", "/data"),))

    def test_rejects_unsafe_paths(self):
        for source in ("/", "/media/../secret", "/media//something", "relative/path", "/media/./file", "/media\\\\Windows"):
            with self.subTest(path=source), self.assertRaises(ValueError):
                translate_path(source, (PathMap("/media", "/data"),))


if __name__ == "__main__":
    unittest.main()
