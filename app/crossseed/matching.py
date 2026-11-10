"""Safe, fast candidate prefiltering for existing-library cross-seeding.

This module performs NO HTTP calls, torrent registration, disk hashing or writes.
The size threshold is a *prefilter*, not evidence of binary equivalence.
"""
from dataclasses import dataclass
from enum import Enum

DEFAULT_EXTRA_BYTES = 1_000_000


class CandidateStatus(str, Enum):
    REJECTED_SIZE = "rejected_size"
    POSSIBLE_SIZE_MATCH = "possible_size_match"
    UNKNOWN_SIZE = "unknown_size"


@dataclass(frozen=True, slots=True)
class SizeCandidate:
    """Sizes MUST be in exact bytes, not rounded GiB or UI labels."""
    local_video_bytes: int
    remote_torrent_bytes: int | None


@dataclass(frozen=True, slots=True)
class SizeDecision:
    status: CandidateStatus
    extra_bytes: int | None
    reason: str

    @property
    def eligible_for_metadata_check(self) -> bool:
        # An absent tracker size requires human/metadata investigation,
        # not automatic acceptance or unconditional rejection.
        return self.status in {
            CandidateStatus.POSSIBLE_SIZE_MATCH,
            CandidateStatus.UNKNOWN_SIZE,
        }


def filter_torrent_by_size(
    candidate: SizeCandidate,
    *,
    max_extra_bytes: int = DEFAULT_EXTRA_BYTES,
) -> SizeDecision:
    """Preselect torrents whose total size is [local_size, local_size + 1 MB].

    This intentionally rejects torrents smaller than the full local video:
    they cannot contain the entire unchanged file. A slightly bigger torrent
    may contain tiny ancillary NFO/SFV/TXT files.

    IMPORTANT:
    - Tracker-reported torrent sizes may be rounded. If so, UNKNOWN_SIZE
      should be used until an exact byte count is retrieved.
    - Equal sizes are NOT proof of identical content.
    - Multi-file torrents still require payload mapping and piece verification.
    - Never add a torrent or trigger downloading based on this result alone.
    """
    if isinstance(candidate.local_video_bytes, bool) or not isinstance(candidate.local_video_bytes, int) or candidate.local_video_bytes < 0:
        raise ValueError("local_video_bytes must be a nonnegative integer")
    if isinstance(max_extra_bytes, bool) or not isinstance(max_extra_bytes, int) or max_extra_bytes < 0:
        raise ValueError("max_extra_bytes must be a nonnegative integer")
    remote = candidate.remote_torrent_bytes
    if remote is None:
        return SizeDecision(CandidateStatus.UNKNOWN_SIZE, None, "Tracker did not provide an exact size")
    if isinstance(remote, bool) or not isinstance(remote, int) or remote < 0:
        raise ValueError("remote_torrent_bytes must be a nonnegative integer or None")

    delta = remote - candidate.local_video_bytes
    if delta < 0:
        return SizeDecision(CandidateStatus.REJECTED_SIZE, delta, "Torrent is smaller than local file")
    if delta > max_extra_bytes:
        return SizeDecision(CandidateStatus.REJECTED_SIZE, delta, "Torrent exceeds extra-size tolerance")
    return SizeDecision(CandidateStatus.POSSIBLE_SIZE_MATCH, delta, "Possible payload size; binary verification still required")
