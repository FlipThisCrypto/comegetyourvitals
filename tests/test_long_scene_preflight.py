from __future__ import annotations

import json
import copy
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from long_scene_contract import load_character_registry, load_manifest  # noqa: E402
from long_scene_preflight import run_preflight  # noqa: E402


class LongScenePreflightTests(unittest.TestCase):
    def fixture(self, root: Path, *, missing: bool = False, small: bool = False) -> tuple[Path, Path]:
        size = (640, 360) if small else (848, 480)
        names = ["start.png", "end-0.png", "end-1.png", "end-2.png", "end-3.png"]
        for name in names:
            if not missing or name != "end-2.png":
                Image.new("RGB", size, "navy").save(root / name)
        manifest = {
            "schema_version": 1,
            "scenes": [{
                "scene_id": "preflight-scene",
                "start_frame": "start.png",
                "location": "center station",
                "cast": ["NURSE_RAINBOW", "NURSE_ORCA"],
                "singer": "NURSE_RAINBOW",
                "camera_axis": "viewer-facing",
                "wardrobe_lock": "canonical scrubs",
                "beats": [{
                    "prompt": f"Distinct action {index}", "end_frame": f"end-{index}.png",
                    "singing": index > 1, "focus": ["NURSE_RAINBOW"],
                } for index in range(4)],
            }],
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        registry = {
            "schema_version": 1,
            "nurses": [
                {"id": "NURSE_RAINBOW", "species": "rainbow fish", "identifying_feature": "rainbow tail"},
                {"id": "NURSE_ORCA", "species": "orca", "identifying_feature": "white eye patch"},
            ],
            "clients": [],
        }
        registry_path = root / "registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        return manifest_path, registry_path

    def test_valid_job_passes_and_records_planned_duration(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, registry_path = self.fixture(root)
            report = run_preflight(
                load_manifest(manifest), load_character_registry(registry_path), root / "preflight.json"
            )
            self.assertTrue(report["passed"])
            self.assertEqual(report["planned_seconds"], 40)
            self.assertEqual(len(report["anchors"]), 5)

    def test_missing_anchor_fails_before_render(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, registry_path = self.fixture(root, missing=True)
            with self.assertRaisesRegex(RuntimeError, "missing"):
                run_preflight(load_manifest(manifest), load_character_registry(registry_path), root / "preflight.json")

    def test_low_resolution_anchor_fails_before_render(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, registry_path = self.fixture(root, small=True)
            with self.assertRaisesRegex(RuntimeError, "resolution_below"):
                run_preflight(load_manifest(manifest), load_character_registry(registry_path), root / "preflight.json")

    def test_missing_runtime_paths_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, registry_path = self.fixture(root)
            with self.assertRaisesRegex(RuntimeError, "missing workflow"):
                run_preflight(
                    load_manifest(manifest), load_character_registry(registry_path), root / "preflight.json",
                    workflow=root / "missing-workflow.json", rife_runtime=root / "missing-rife",
                )

    def test_duplicate_creative_scene_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, registry_path = self.fixture(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            duplicate = copy.deepcopy(payload["scenes"][0])
            duplicate["scene_id"] = "duplicate-scene"
            payload["scenes"].append(duplicate)
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "duplicates creative definition"):
                run_preflight(load_manifest(manifest), load_character_registry(registry_path), root / "preflight.json")


if __name__ == "__main__":
    unittest.main()
