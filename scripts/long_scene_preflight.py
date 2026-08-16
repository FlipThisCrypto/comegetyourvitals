#!/usr/bin/env python3
"""Fail-fast validation for expensive long-scene generation jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from long_scene_contract import Scene, load_character_registry, load_manifest, validate_scene_cast


TARGET_WIDTH = 848
TARGET_HEIGHT = 480
TARGET_ASPECT = TARGET_WIDTH / TARGET_HEIGHT


@dataclass(frozen=True)
class AnchorCheck:
    path: str
    width: int | None
    height: int | None
    mode: str | None
    sha256: str | None
    valid: bool
    errors: tuple[str, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_anchor(path: Path) -> AnchorCheck:
    errors: list[str] = []
    width = height = None
    mode = digest = None
    if not path.is_file():
        errors.append("missing")
    else:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height, mode = image.width, image.height, image.mode
            digest = file_sha256(path)
            if width < TARGET_WIDTH or height < TARGET_HEIGHT:
                errors.append("resolution_below_848x480")
            aspect_error = abs(width / height - TARGET_ASPECT) / TARGET_ASPECT
            if aspect_error > 0.10:
                errors.append("aspect_ratio_more_than_10_percent_from_16_9")
            if mode not in {"RGB", "RGBA"}:
                errors.append("unsupported_color_mode")
        except (OSError, ValueError) as error:
            errors.append(f"undecodable:{type(error).__name__}")
    return AnchorCheck(str(path), width, height, mode, digest, not errors, tuple(errors))


def creative_fingerprint(scene: Scene) -> str:
    payload = {
        "location": scene.location.casefold().strip(),
        "cast": sorted(scene.cast),
        "singer": scene.singer,
        "camera_axis": scene.camera_axis.casefold().strip(),
        "prompts": [beat.prompt.casefold().strip() for beat in scene.beats],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def endpoint_health(endpoint: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/system_stats", timeout=10) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            json.loads(response.read().decode())
        return True, "ok"
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


def run_preflight(
    scenes: tuple[Scene, ...],
    registry: dict[str, dict[str, object]],
    report_path: Path,
    *,
    workflow: Path | None = None,
    rife_runtime: Path | None = None,
    endpoints: tuple[str, ...] = (),
) -> dict[str, object]:
    errors: list[str] = []
    validate_scene_cast(scenes, registry)
    anchors: dict[str, AnchorCheck] = {}
    fingerprints: dict[str, str] = {}
    for scene in scenes:
        fingerprint = creative_fingerprint(scene)
        if fingerprint in fingerprints:
            errors.append(f"scene {scene.scene_id} duplicates creative definition of {fingerprints[fingerprint]}")
        fingerprints[fingerprint] = scene.scene_id
        for path in (scene.start_frame, *(beat.end_frame for beat in scene.beats)):
            key = str(path)
            if key not in anchors:
                anchors[key] = check_anchor(path)
            if not anchors[key].valid:
                errors.extend(f"anchor {path}: {problem}" for problem in anchors[key].errors)
    runtime: dict[str, object] = {}
    if workflow is not None:
        runtime["workflow"] = str(workflow)
        if not workflow.is_file():
            errors.append(f"missing workflow: {workflow}")
    if rife_runtime is not None:
        required = (
            rife_runtime / ".venv/bin/python",
            rife_runtime / "inference_video.py",
            rife_runtime / "train_log",
        )
        runtime["rife_required"] = [str(path) for path in required]
        for path in required:
            if not path.exists():
                errors.append(f"missing RIFE runtime path: {path}")
    endpoint_results = {}
    for endpoint in endpoints:
        healthy, detail = endpoint_health(endpoint)
        endpoint_results[endpoint] = {"healthy": healthy, "detail": detail}
        if not healthy:
            errors.append(f"unhealthy endpoint {endpoint}: {detail}")
    report = {
        "schema_version": 1,
        "passed": not errors,
        "scene_count": len(scenes),
        "planned_seconds": len(scenes) * 40,
        "unique_creative_fingerprints": len(fingerprints),
        "anchors": [asdict(check) for check in anchors.values()],
        "runtime": runtime,
        "endpoints": endpoint_results,
        "errors": errors,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("Long-scene preflight failed:\n" + "\n".join(errors))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--character-registry", type=Path, default=Path("character-registry.json"))
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--rife-runtime", type=Path)
    parser.add_argument("--endpoint", action="append", default=[])
    args = parser.parse_args()
    scenes = load_manifest(args.manifest)
    registry = load_character_registry(args.character_registry)
    run_preflight(
        scenes, registry, args.report, workflow=args.workflow, rife_runtime=args.rife_runtime,
        endpoints=tuple(args.endpoint),
    )
    print(args.report)


if __name__ == "__main__":
    main()
