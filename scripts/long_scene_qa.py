#!/usr/bin/env python3
"""Visual diagnostics and human approval binding for generated scene segments."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from long_scene_contract import DELIVERY_FPS, SEGMENT_SECONDS, video_matches


SAMPLE_FPS = 2
SAMPLE_COUNT = SEGMENT_SECONDS * SAMPLE_FPS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rgb(path: Path, size: tuple[int, int] = (320, 180)) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB").resize(size, Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


def similarity(left: Path, right: Path) -> float:
    return float(1.0 - np.mean(np.abs(load_rgb(left) - load_rgb(right))))


def extract_review_frames(video: Path, directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pattern = directory / "sample-%02d.png"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vf", f"fps={SAMPLE_FPS},scale=320:180:flags=lanczos", "-frames:v", str(SAMPLE_COUNT), str(pattern),
    ], check=True)
    frames = sorted(directory.glob("sample-*.png"))
    if len(frames) != SAMPLE_COUNT:
        raise RuntimeError(f"Expected {SAMPLE_COUNT} QA samples, found {len(frames)}")
    return frames


def extract_boundary(video: Path, output: Path, *, final: bool) -> None:
    if final:
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "json", str(video),
        ]))
        selector = int(probe["streams"][0]["nb_frames"]) - 1
    else:
        selector = 0
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vf", f"select=eq(n\\,{selector}),scale=320:180:flags=lanczos", "-frames:v", "1", str(output),
    ], check=True)


def frame_metrics(frames: list[Path]) -> dict[str, float]:
    arrays = [load_rgb(path) for path in frames]
    deltas = np.asarray([np.mean(np.abs(b - a)) for a, b in zip(arrays, arrays[1:])], dtype=np.float32)
    luminance = [float(np.mean(array)) for array in arrays]
    sharpness = []
    for array in arrays:
        gray = np.mean(array, axis=2)
        gx = np.abs(np.diff(gray, axis=1)).mean()
        gy = np.abs(np.diff(gray, axis=0)).mean()
        sharpness.append(float(gx + gy))
    median_delta = float(np.median(deltas))
    median_sharpness = float(np.median(sharpness))
    return {
        "median_frame_delta": median_delta,
        "max_frame_delta": float(np.max(deltas)),
        "static_pair_fraction": float(np.mean(deltas < 0.0025)),
        "black_sample_fraction": float(np.mean(np.asarray(luminance) < 0.025)),
        "low_detail_fraction": float(np.mean(np.asarray(sharpness) < max(0.003, median_sharpness * 0.35))),
        "median_detail": median_sharpness,
    }


def analyze_segment(video: Path, start_anchor: Path, end_anchor: Path, output_directory: Path) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    samples = extract_review_frames(video, output_directory / "samples")
    first = output_directory / "first-frame.png"
    last = output_directory / "last-frame.png"
    extract_boundary(video, first, final=False)
    extract_boundary(video, last, final=True)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vf", "fps=2,scale=320:180:flags=lanczos,tile=5x4", "-frames:v", "1", str(output_directory / "review-contact-sheet.jpg"),
    ], check=True)
    metrics = frame_metrics(samples)
    metrics["start_anchor_similarity"] = similarity(first, start_anchor)
    metrics["end_anchor_similarity"] = similarity(last, end_anchor)
    reasons: list[str] = []
    if not video_matches(video, seconds=SEGMENT_SECONDS, fps=DELIVERY_FPS):
        reasons.append("timing_contract_failed")
    if metrics["start_anchor_similarity"] < 0.68:
        reasons.append("start_anchor_drift")
    if metrics["end_anchor_similarity"] < 0.68:
        reasons.append("end_anchor_drift")
    if metrics["static_pair_fraction"] > 0.30:
        reasons.append("excessive_static_motion")
    if metrics["black_sample_fraction"] > 0.05:
        reasons.append("unexpected_black_frames")
    if metrics["low_detail_fraction"] > 0.25:
        reasons.append("excessive_blur_or_detail_loss")
    jump_limit = max(0.20, metrics["median_frame_delta"] * 4.5)
    if metrics["max_frame_delta"] > jump_limit:
        reasons.append("possible_internal_cut_or_morph_spike")
    report = {
        "schema_version": 1,
        "video": str(video.resolve()),
        "video_sha256": sha256(video),
        "start_anchor_sha256": sha256(start_anchor),
        "end_anchor_sha256": sha256(end_anchor),
        "metrics": metrics,
        "metrics_pass": not reasons,
        "failure_reasons": reasons,
        "contact_sheet": str((output_directory / "review-contact-sheet.jpg").resolve()),
        "human_review_required": True,
    }
    report_path = output_directory / "qa-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def report_fingerprint(report: dict[str, object]) -> str:
    stable = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(stable).hexdigest()


def approval_status(output_directory: Path, report: dict[str, object]) -> str:
    review_path = output_directory / "review.json"
    if not review_path.is_file():
        return "pending"
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "pending"
    if review.get("report_fingerprint") != report_fingerprint(report):
        return "stale"
    return str(review.get("decision", "pending"))


def record_decision(output_directory: Path, decision: str, reviewer: str, note: str, *, override: bool = False) -> Path:
    report_path = output_directory / "qa-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if decision == "approved" and not report.get("metrics_pass") and not override:
        raise ValueError("metrics failed; use --override with a review note to approve explicitly")
    if override and not note.strip():
        raise ValueError("an override requires a non-empty review note")
    review = {
        "schema_version": 1,
        "decision": decision,
        "reviewer": reviewer,
        "note": note,
        "metrics_override": override,
        "report_fingerprint": report_fingerprint(report),
    }
    output = output_directory / "review.json"
    output.write_text(json.dumps(review, indent=2), encoding="utf-8")
    return output


def archive_attempt(segment_directory: Path) -> Path:
    archive_root = segment_directory / "rejected-attempts"
    archive_root.mkdir(parents=True, exist_ok=True)
    attempt = archive_root / f"attempt-{len(list(archive_root.glob('attempt-*'))) + 1:03d}"
    attempt.mkdir()
    for name in (
        "native-8fps.mp4", "delivery-60fps.mp4", "interpolated-fullspeed-60fps.mp4", "continuity-end.png",
        "generation-spec.json", "qa",
    ):
        source = segment_directory / name
        if source.exists():
            shutil.move(str(source), str(attempt / name))
    return attempt


def archive_scene_delivery(scene_directory: Path) -> Path | None:
    outputs = list(scene_directory.glob("*-40s-60fps.mp4"))
    if not outputs:
        return None
    archive_root = scene_directory / "stale-assemblies"
    archive_root.mkdir(parents=True, exist_ok=True)
    archive = archive_root / f"assembly-{len(list(archive_root.glob('assembly-*'))) + 1:03d}.mp4"
    shutil.move(str(outputs[0]), str(archive))
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    decide = subparsers.add_parser("decide")
    decide.add_argument("qa_directory", type=Path)
    decide.add_argument("decision", choices=("approved", "rejected"))
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--note", default="")
    decide.add_argument("--override", action="store_true")
    archive = subparsers.add_parser("archive-rejected")
    archive.add_argument("segment_directory", type=Path)
    args = parser.parse_args()
    if args.command == "decide":
        print(record_decision(args.qa_directory, args.decision, args.reviewer, args.note, override=args.override))
    else:
        print(archive_attempt(args.segment_directory))


if __name__ == "__main__":
    main()
