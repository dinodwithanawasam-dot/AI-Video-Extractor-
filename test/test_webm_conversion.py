import sys
import subprocess
import unittest
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.ingestion import ensure_mp4_format


class TestWebMConversion(unittest.TestCase):

    def setUp(self):
        self.temp_dir = ROOT_DIR / "data" / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.test_webm = self.temp_dir / "test_sample_unit.webm"
        self.test_mp4 = self.temp_dir / "test_sample_unit.mp4"

        # Generate a 1-second synthetic WebM file (VP9 + Opus)
        cmd_gen = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=640x360:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libvpx-vp9", "-c:a", "libopus",
            str(self.test_webm)
        ]
        subprocess.run(cmd_gen, check=True, capture_output=True)

    def tearDown(self):
        if self.test_webm.exists():
            self.test_webm.unlink()
        if self.test_mp4.exists():
            self.test_mp4.unlink()

    def test_ensure_mp4_format_converts_webm_to_h264_aac(self):
        """WebM input should be converted to standard MP4 with H.264 video and AAC audio."""
        converted_path = ensure_mp4_format(str(self.test_webm))
        self.assertTrue(Path(converted_path).exists())
        self.assertTrue(converted_path.endswith(".mp4"))

        # Probe streams
        probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", converted_path]
        res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        streams = res.stdout.strip().split()

        self.assertIn("h264", streams)
        self.assertIn("aac", streams)

    def test_ensure_mp4_format_skips_already_mp4(self):
        """If file is already .mp4, it should return the exact same path immediately."""
        fake_mp4 = self.temp_dir / "existing.mp4"
        fake_mp4.write_text("dummy")
        try:
            result = ensure_mp4_format(str(fake_mp4))
            self.assertEqual(result, str(fake_mp4))
        finally:
            if fake_mp4.exists():
                fake_mp4.unlink()


if __name__ == "__main__":
    unittest.main()
