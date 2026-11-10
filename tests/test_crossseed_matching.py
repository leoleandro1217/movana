"""Unit tests for cross-seed candidate size prefilter."""
import unittest

from app.crossseed.matching import (
    CandidateStatus,
    SizeCandidate,
    filter_torrent_by_size,
)


class SizeFilterTests(unittest.TestCase):
    LOCAL = 5_000_000_000

    def evaluate(self, remote):
        return filter_torrent_by_size(SizeCandidate(self.LOCAL, remote))

    def test_exact_size_passes_as_unverified(self):
        decision = self.evaluate(self.LOCAL)
        self.assertEqual(decision.status, CandidateStatus.POSSIBLE_SIZE_MATCH)
        self.assertEqual(decision.extra_bytes, 0)

    def test_exactly_one_decimal_mb_passes(self):
        self.assertEqual(self.evaluate(self.LOCAL + 1_000_000).status, CandidateStatus.POSSIBLE_SIZE_MATCH)

    def test_just_above_threshold_rejected(self):
        self.assertEqual(self.evaluate(self.LOCAL + 1_000_001).status, CandidateStatus.REJECTED_SIZE)

    def test_smaller_torrent_rejected_even_by_one_byte(self):
        self.assertEqual(self.evaluate(self.LOCAL - 1).status, CandidateStatus.REJECTED_SIZE)

    def test_small_ancillary_files_pass_prefilter(self):
        self.assertEqual(self.evaluate(self.LOCAL + 30_000).extra_bytes, 30_000)

    def test_missing_exact_size_never_automatically_verified(self):
        decision = self.evaluate(None)
        self.assertEqual(decision.status, CandidateStatus.UNKNOWN_SIZE)
        self.assertTrue(decision.eligible_for_metadata_check)

    def test_invalid_sizes_fail(self):
        for size in (-1, "5 GiB", 1.5, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                filter_torrent_by_size(SizeCandidate(self.LOCAL, size))

    def test_negative_tolerance_rejected(self):
        with self.assertRaises(ValueError):
            filter_torrent_by_size(SizeCandidate(self.LOCAL, self.LOCAL), max_extra_bytes=-1)


if __name__ == "__main__":
    unittest.main()
