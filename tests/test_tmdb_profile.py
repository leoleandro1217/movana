"""TMDb profile parsing: only source-backed title, synopsis, genres and art."""
import unittest
from unittest.mock import patch

from app.tmdb_profile import fetch_profile, sanitize_profile
from app.tmdb_languages import ProviderUnavailable


class ProfileTests(unittest.TestCase):
    def test_original_title_and_english_overview(self):
        data = {"id": 10, "original_title": "Le vrai titre", "overview": "Synopsis verified.",
                "release_date": "2007-04-09", "poster_path": "/abc.jpg",
                "genres": [{"name": "Drama"}], "translations": {"translations": [
                    {"iso_639_1": "fr", "iso_3166_1": "FR", "data": {"title": "Titre FR"}}
                ]}}
        with patch("app.tmdb_profile._request", return_value=data) as mock:
            result = fetch_profile("movie", 10, "original")
        self.assertEqual(result["title"], "Le vrai titre")
        self.assertEqual(result["overview"], "Synopsis verified.")
        self.assertEqual(result["overview_language"], "en-US")
        self.assertEqual(result["poster_path"], "/abc.jpg")
        self.assertEqual(result["genres"], ["Drama"])
        self.assertIn("language=en-US", mock.call_args.args[0])

    def test_uses_real_french_translation_and_region(self):
        data = {"id": 8, "original_name": "Original", "translations": {"translations": [
            {"iso_639_1": "fr", "iso_3166_1": "CA", "data": {"name": "Canadian"}},
            {"iso_639_1": "fr", "iso_3166_1": "FR", "data": {"name": "French"}}
        ]}}
        self.assertEqual(sanitize_profile("tv", 8, data, "fr-FR")["title"], "French")
        self.assertEqual(sanitize_profile("tv", 8, data, "fr-CH")["title"], "Original")

    def test_no_translation_is_never_fabricated(self):
        data = {"id": 8, "original_name": "Real", "name": "Unverified localized name"}
        result = sanitize_profile("tv", 8, data, "fr-FR")
        self.assertEqual(result["title"], "Real")
        self.assertIsNone(result["overview"])
        self.assertIsNone(result["poster_path"])

    def test_invalid_remote_paths_ignored(self):
        for path in ("http://example.org/poster.jpg", "../a.jpg", "/a.svg"):
            with self.subTest(path=path):
                obj = sanitize_profile("movie", 1, {"id": 1, "original_title": "Real", "poster_path": path}, "original")
                self.assertIsNone(obj["poster_path"])

    def test_invalid_identity_cannot_be_displayed(self):
        with self.assertRaises(ProviderUnavailable):
            sanitize_profile("movie", 1, {"id": 2, "original_title": "Unrelated"}, "original")
        with self.assertRaises(ProviderUnavailable):
            sanitize_profile("movie", 1, {"id": 1, "title": "Not original"}, "original")

    def test_rejects_unsafe_type_and_locale(self):
        for media_type, provider_id, language in [
            ("person", 2, "original"), ("movie", -1, "original"), ("movie", 2, "random-locale")
        ]:
            with self.subTest(media_type=media_type, language=language), self.assertRaises(ValueError):
                fetch_profile(media_type, provider_id, language)


if __name__ == "__main__":
    unittest.main()
