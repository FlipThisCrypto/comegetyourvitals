from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from long_scene_qa import (  # noqa: E402
    analyze_segment,
    approval_status,
    archive_attempt,
    archive_scene_delivery,
    record_decision,
    report_fingerprint,
)


class LongSceneQaTests(unittest.TestCase):
    def write_report(self, directory: Path, *, passed: bool = True) -> dict[str, object]:
        report = {
            "schema_version": 1,
            "video_sha256": "video-a",
            "start_anchor_sha256": "start-a",
            "end_anchor_sha256": "end-a",
            "metrics_pass": passed,
            "failure_reasons": [] if passed else ["anchor_drift"],
        }
        (directory / "qa-report.json").write_text(json.dumps(report), encoding="utf-8")
        return report

    def test_approval_is_bound_to_exact_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report = self.write_report(root)
            record_decision(root, "approved", "qa-user", "looks clean")
            self.assertEqual(approval_status(root, report), "approved")
            changed = dict(report, video_sha256="video-b")
            self.assertEqual(approval_status(root, changed), "stale")

    def test_failed_metrics_cannot_be_silently_approved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.write_report(root, passed=False)
            with self.assertRaisesRegex(ValueError, "metrics failed"):
                record_decision(root, "approved", "qa-user", "")

    def test_override_requires_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report = self.write_report(root, passed=False)
            with self.assertRaisesRegex(ValueError, "review note"):
                record_decision(root, "approved", "qa-user", "", override=True)
            record_decision(root, "approved", "qa-user", "false positive inspected", override=True)
            self.assertEqual(approval_status(root, report), "approved")

    def test_rejected_attempt_is_archived_without_touching_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "native-8fps.mp4").write_bytes(b"native")
            sibling = root.parent / "other-segment.mp4"
            sibling.write_bytes(b"keep")
            archive = archive_attempt(root)
            self.assertEqual((archive / "native-8fps.mp4").read_bytes(), b"native")
            self.assertTrue(sibling.is_file())

    def test_analysis_creates_dense_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            video = root / "segment.mp4"
            first = root / "first.png"
            last = root / "last.png"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=160x90:rate=60:duration=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
            ], check=True)
            for selector, output in ((0, first), (599, last)):
                subprocess.run([
                    "ffmpeg", "-y", "-v", "error", "-i", str(video),
                    "-vf", f"select=eq(n\\,{selector})", "-frames:v", "1", str(output),
                ], check=True)
            qa = root / "qa"
            report = analyze_segment(video, first, last, qa)
            self.assertTrue((qa / "qa-report.json").is_file())
            self.assertTrue((qa / "review-contact-sheet.jpg").is_file())
            self.assertEqual(len(list((qa / "samples").glob("sample-*.png"))), 20)
            self.assertTrue(report["metrics_pass"])

    def test_stale_scene_delivery_is_archived_recoverably(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            delivery = root / "scene-40s-60fps.mp4"
            delivery.write_bytes(b"old assembly")
            archived = archive_scene_delivery(root)
            self.assertIsNotNone(archived)
            self.assertEqual(archived.read_bytes(), b"old assembly")
            self.assertFalse(delivery.exists())


if __name__ == "__main__":
    unittest.main()
