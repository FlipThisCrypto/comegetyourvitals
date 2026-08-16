from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_wan_full60.py"


def load_delivery_validator():
    """Load only the dependency-free validator from the production script."""
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("def delivery_is_valid(")
    end = source.index("\n\ndef assemble", start)
    namespace = {"Path": Path, "json": __import__("json"), "subprocess": subprocess}
    exec(source[start:end], namespace)
    return namespace["delivery_is_valid"]


class FullSpeedDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.delivery_is_valid = staticmethod(load_delivery_validator())

    def make_clip(self, path: Path, duration: int, fps: int = 60) -> None:
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"testsrc2=size=160x90:rate={fps}:duration={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ], check=True)

    def test_accepts_ten_second_600_frame_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery.mp4"
            self.make_clip(output, duration=10)
            self.assertTrue(self.delivery_is_valid(output))

    def test_rejects_old_five_second_speed_compressed_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery.mp4"
            self.make_clip(output, duration=5)
            self.assertFalse(self.delivery_is_valid(output))

    def test_rejects_wrong_frame_rate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delivery.mp4"
            self.make_clip(output, duration=10, fps=30)
            self.assertFalse(self.delivery_is_valid(output))


if __name__ == "__main__":
    unittest.main()
