from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from long_scene_contract import (  # noqa: E402
    SCENE_FRAMES,
    continuity_steps,
    extract_last_frame,
    load_manifest,
    performance_directive,
    video_matches,
)


class LongSceneContractTests(unittest.TestCase):
    def manifest(self, directory: Path, *, beats: int = 4) -> Path:
        path = directory / "manifest.json"
        payload = {
            "schema_version": 1,
            "scenes": [{
                "scene_id": "test-scene",
                "start_frame": "start.png",
                "beats": [{
                    "prompt": f"Beat {index}", "end_frame": f"end-{index}.png", "singing": index >= 2,
                } for index in range(beats)],
            }],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_manifest_builds_four_chained_steps(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            scene = load_manifest(self.manifest(root))[0]
            steps = continuity_steps(scene, root / "output")
            self.assertEqual(len(steps), 4)
            for previous, current in zip(steps, steps[1:]):
                self.assertEqual(current.start_frame, previous.continuity_frame)

    def test_manifest_rejects_non_40_second_scene(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ValueError, "exactly 4 beats"):
                load_manifest(self.manifest(Path(raw), beats=3))

    def test_singing_directives_are_unambiguous(self) -> None:
        self.assertIn("Only the female lead sings", performance_directive(True))
        self.assertIn("No character lip-syncs", performance_directive(False))

    def test_40_second_delivery_contract_is_2400_frames(self) -> None:
        self.assertEqual(SCENE_FRAMES, 2400)
        with tempfile.TemporaryDirectory() as raw:
            clip = Path(raw) / "scene.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=black:size=64x36:rate=60:duration=40", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
            ], check=True)
            self.assertTrue(video_matches(clip, seconds=40))

    def test_extracts_actual_last_frame_for_next_segment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            clip = Path(raw) / "native.mp4"
            frame = Path(raw) / "continuity-end.png"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=64x36:rate=8:duration=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
            ], check=True)
            extract_last_frame(clip, frame)
            self.assertTrue(frame.is_file())
            self.assertGreater(frame.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
