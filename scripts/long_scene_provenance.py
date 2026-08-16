#!/usr/bin/env python3
"""Content-addressed generation specifications for safe resume and retries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def attempt_number(segment_directory: Path) -> int:
    archive = segment_directory / "rejected-attempts"
    return len(list(archive.glob("attempt-*"))) + 1 if archive.is_dir() else 1


def diversified_seed(scene_id: str, beat_index: int, attempt: int) -> int:
    if attempt < 1:
        raise ValueError("attempt must be positive")
    base = 910_000 + sum(ord(char) for char in scene_id) * 31 + beat_index * 997
    return base + (attempt - 1) * 1_000_003


def build_spec(
    *,
    scene_id: str,
    segment: int,
    attempt: int,
    prompt: str,
    negative_prompt: str,
    start_frame: Path,
    end_frame: Path,
    seed: int,
    model: str,
    provider_settings: dict[str, object],
    width: int,
    height: int,
    duration_seconds: int,
    native_fps: int,
    delivery_fps: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "scene_id": scene_id,
        "segment": segment,
        "attempt": attempt,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "start_frame": str(start_frame.resolve()),
        "start_frame_sha256": file_sha256(start_frame),
        "end_frame": str(end_frame.resolve()),
        "end_frame_sha256": file_sha256(end_frame),
        "seed": seed,
        "model": model,
        "provider_settings": provider_settings,
        "width": width,
        "height": height,
        "duration_seconds": duration_seconds,
        "native_fps": native_fps,
        "delivery_fps": delivery_fps,
    }


def fingerprint(spec: dict[str, object]) -> str:
    canonical = {key: value for key, value in spec.items() if key != "fingerprint"}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def spec_matches(path: Path, expected: dict[str, object]) -> bool:
    if not path.is_file():
        return False
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return fingerprint(actual) == fingerprint(expected)


def write_spec(path: Path, spec: dict[str, object]) -> None:
    payload = dict(spec, fingerprint=fingerprint(spec))
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
