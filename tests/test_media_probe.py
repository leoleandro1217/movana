"""ffprobe parsing and command safety, with no actual media files."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.media_probe import ProbeError, inspect_file, parse_probe


class MediaProbeTests(unittest.TestCase):
    def test_video_audio_subtitle_languages_and_dimensions(self):
        data = {"format": {"duration": "123.456"}, "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160},
            {"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6,
             "tags": {"language": "fra"}},
            {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2,
             "tags": {"language": "eng"}},
            {"index": 3, "codec_type": "subtitle", "codec_name": "subrip",
             "tags": {"language": "fra"}},
        ]}
        result = parse_probe(data)
        self.assertEqual(result["video"][0]["width"], 3840)
        self.assertEqual(result["video"][0]["height"], 2160)
        self.assertEqual([x["language"] for x in result["audio"]], ["fra", "eng"])
        self.assertEqual(result["subtitles"][0]["codec"], "subrip")
        self.assertEqual(result["duration_seconds"], 123.456)

    def test_missing_tags_remain_unknown(self):
        result = parse_probe({"streams": [{"codec_type": "audio", "codec_name": "aac"}]})
        self.assertIsNone(result["audio"][0]["language"])
        self.assertIsNone(result["audio"][0]["channels"])
        self.assertIsNone(result["duration_seconds"])

    def test_invalid_data_is_rejected(self):
        for payload in (None, [], {"streams": "not-a-list"}):
            with self.subTest(payload=payload), self.assertRaises(ProbeError):
                parse_probe(payload)

    def test_on_demand_read_only_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "media.mkv"
            file.write_bytes(b"dummy")
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"streams": []}).encode(), stderr=b""
            )
            with patch("app.media_probe.subprocess.run", return_value=completed) as mock:
                result = inspect_file(file)
            self.assertEqual(result["audio"], [])
            argv = mock.call_args.args[0]
            self.assertEqual(argv[0], "ffprobe")
            self.assertIn("-show_entries", argv)
            self.assertNotIn("-y", argv)
            self.assertEqual(argv[-1], str(file))
            self.assertEqual(mock.call_args.kwargs["timeout"], 25)

    def test_symlink_is_not_probed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "real.mkv"
            target.write_bytes(b"x")
            link = Path(tmp) / "link.mkv"
            link.symlink_to(target)
            with self.assertRaises(ProbeError):
                inspect_file(link)

    def test_timeout_does_not_hang_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "media.mkv"
            file.write_bytes(b"x")
            with patch("app.media_probe.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 25)):
                with self.assertRaises(ProbeError):
                    inspect_file(file)


if __name__ == "__main__":
    unittest.main()
