"""TMDb language selection must never synthesize translations."""
import unittest
from unittest.mock import patch

from app import tmdb_languages as mod


class LocaleTests(unittest.TestCase):
    def test_original_is_available_without_provider_key(self):
        with patch.object(mod, "supported_locales", side_effect=AssertionError("Should not request network")):
            mod.validate_preferences("tmdb", "original", "original")

    def test_locale_must_come_from_provider(self):
        with patch.object(mod, "supported_locales", return_value=["fr-FR", "en-US"]):
            mod.validate_preferences("tmdb", "fr-FR", "original")
            with self.assertRaises(ValueError):
                mod.validate_preferences("tmdb", "fr-CH", "original")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError):
            mod.validate_preferences("omdb", "original", "original")

    def test_missing_translation_returns_original(self):
        entries = [{"iso_639_1": "en", "iso_3166_1": "US", "data": {"title": "The Movie"}}]
        self.assertEqual(mod.select_title("Titre original", entries, "fr-FR"), "Titre original")

    def test_exact_locale_required(self):
        entries = [{"iso_639_1": "fr", "iso_3166_1": "CA", "data": {"title": "Titre canadien"}}]
        self.assertEqual(mod.select_title("Original", entries, "fr-FR"), "Original")

    def test_existing_translation(self):
        entries = [{"iso_639_1": "fr", "iso_3166_1": "FR", "data": {"title": "Titre français"}}]
        self.assertEqual(mod.select_title("Original", entries, "fr-FR"), "Titre français")

    def test_no_original_no_translation_never_invents(self):
        self.assertIsNone(mod.select_title(None, [], "fr-FR"))

    def test_empty_translated_title_falls_back(self):
        data = [{"iso_639_1": "fr", "iso_3166_1": "FR", "data": {"title": "   "}}]
        self.assertEqual(mod.select_title("Original", data, "fr-FR"), "Original")


if __name__ == "__main__":
    unittest.main()
