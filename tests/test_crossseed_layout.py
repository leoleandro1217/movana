"""Offline manifest comparison: never equate sizes with verified pieces."""
import unittest

from app.crossseed.layout import Coverage, ManifestFile as F, compare_layout


class LayoutTests(unittest.TestCase):
    def test_unique_size_renamed_film_full_but_unverified(self):
        got = compare_layout((F("Films/renamed.mkv", 500),), (F("release/original.mkv", 500),))
        self.assertEqual(got.coverage, Coverage.FULL)
        self.assertEqual(got.mappings[0].local_path, "Films/renamed.mkv")
        self.assertFalse(got.verified)

    def test_episode_in_season_pack_is_partial(self):
        got = compare_layout((F("Show/E01.mkv", 900),),
                             (F("Season/ep1.mkv", 900), F("Season/ep2.mkv", 1100)))
        self.assertEqual(got.coverage, Coverage.PARTIAL)
        self.assertEqual(got.missing_torrent_paths, ("Season/ep2.mkv",))

    def test_equal_sizes_without_unique_mapping_are_ambiguous(self):
        got = compare_layout((F("a.mkv", 500), F("b.mkv", 500)),
                             (F("x.mkv", 500), F("y.mkv", 500)))
        self.assertEqual(got.coverage, Coverage.AMBIGUOUS)
        self.assertEqual(len(got.mappings), 0)

    def test_same_path_disambiguates_duplicate_sizes(self):
        got = compare_layout((F("a.mkv", 500), F("b.mkv", 500)),
                             (F("a.mkv", 500), F("b.mkv", 500)))
        self.assertEqual(got.coverage, Coverage.FULL)
        self.assertEqual(len(got.mappings), 2)

    def test_no_match(self):
        got = compare_layout((F("local.mkv", 900),), (F("other.mkv", 901),))
        self.assertEqual(got.coverage, Coverage.NONE)
        self.assertFalse(got.verified)

    def test_unsafe_and_duplicate_paths(self):
        for path in ("/absolute.mkv", "../escape.mkv", "a/../escape.mkv", "a//x.mkv", "a\\\\b.mkv"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    compare_layout((), (F(path, 1),))
        with self.assertRaises(ValueError):
            compare_layout((F("x.mkv", 1), F("x.mkv", 1)), ())

    def test_bools_and_negative_sizes_rejected(self):
        for size in (-1, True, 1.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                compare_layout((F("x.mkv", size),), ())

    def test_empty_torrent_never_matches(self):
        self.assertEqual(compare_layout((F("one.mkv", 5),), ()).coverage, Coverage.NONE)


if __name__ == "__main__":
    unittest.main()
