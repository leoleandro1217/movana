"""Offline tests for safe filename parsing."""
import os
import unittest
from pathlib import Path

os.environ.setdefault("DB_PASSWORD", "test-only")
from app.main import parse_name


class NameParsingTests(unittest.TestCase):
    def test_movie(self):
        self.assertEqual(parse_name(Path("Movies/Alien.1979.1080p.BluRay.mkv")), ("Alien", "movies", 1979))

    def test_tv_episode(self):
        title, category, _ = parse_name(Path("Series/Breaking.Bad.S01E02.1080p.mkv"))
        self.assertEqual((title, category), ("Breaking Bad", "series"))

    def test_anime_directory(self):
        _, category, _ = parse_name(Path("Anime/Dragon.Ball.Z.S01E01.mkv"))
        self.assertEqual(category, "anime")

    def test_unknown_year(self):
        self.assertIsNone(parse_name(Path("Movies/Unknown.Film.mkv"))[2])


if __name__ == "__main__":
    unittest.main()
