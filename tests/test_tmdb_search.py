"""TMDb search tests: provider mocked, no real API or media accessed."""
import unittest
from unittest.mock import patch

from app.tmdb_search import query_candidates


class SearchTests(unittest.TestCase):
    def test_movies_are_unverified_and_preserve_original(self):
        payload = {"results": [
            {"id": 5, "original_title": "Original", "title": "Translated", "release_date": "2001-02-03", "poster_path": "/poster.jpg"},
            {"id": 7, "title": "Without original"},
        ]}
        with patch("app.tmdb_search._request", return_value=payload) as mock:
            result = query_candidates("Movie", "movies", 2001)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["original_title"], "Original")
        self.assertTrue(result[0]["review_required"])
        self.assertIn("/search/movie?", mock.call_args.args[0])
        self.assertIn("year=2001", mock.call_args.args[0])

    def test_series_uses_tv_endpoint_and_year(self):
        with patch("app.tmdb_search._request", return_value={"results": []}) as mock:
            self.assertEqual(query_candidates("Show", "series", 2015), [])
        self.assertIn("/search/tv?", mock.call_args.args[0])
        self.assertIn("first_air_date_year=2015", mock.call_args.args[0])

    def test_animation_is_movie(self):
        with patch("app.tmdb_search._request", return_value={"results": []}) as mock:
            query_candidates("Film", "animation")
        self.assertIn("/search/movie?", mock.call_args.args[0])

    def test_rejects_invalid_and_missing_titles(self):
        for title, kind, year, page in [
            ("", "movies", None, 1), ("Title", "mixed", None, 1),
            ("Title", "movies", 1000, 1), ("Title", "movies", None, 6),
        ]:
            with self.subTest(title=title, kind=kind, year=year, page=page):
                with self.assertRaises(ValueError):
                    query_candidates(title, kind, year, page)

    def test_does_not_invent_dates_or_posters(self):
        with patch("app.tmdb_search._request", return_value={"results": [
            {"id": 123, "original_name": "Real", "first_air_date": "no date", "poster_path": "http://unsafe.local"}
        ]}):
            result = query_candidates("Real", "series")
        self.assertIsNone(result[0]["release_date"])
        self.assertIsNone(result[0]["poster_path"])


if __name__ == "__main__":
    unittest.main()
