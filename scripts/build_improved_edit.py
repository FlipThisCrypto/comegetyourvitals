#!/usr/bin/env python3
"""Build a faster, cleaner, performance-style V2 edit from the Wan source plates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


WIDTH = 848
HEIGHT = 480
FINAL_DURATION = 250.833333
PICTURE_DURATION = 241.74


@dataclass
class EditItem:
    index: int
    timeline_in: float
    duration: float
    section: str
    shot_id: str
    plate_a: int
    plate_b: int | None
    source_in: float
    treatment: str


POOLS = {
    "intro": [1, 2, 8, 15, 22],
    "verse": [2, 4, 8, 9, 10, 11, 15, 16, 18, 24, 25, 3, 17],
    "chorus": [5, 7, 12, 14, 19, 21],
    "bridge": [6, 13, 20],
    "outro": [21, 14, 7, 5, 1],
}

# These clips contain the most visible source smears in the first assembly.  They
# remain useful, but only in their cleaner windows.
SAFE_WINDOWS = {
    17: [(0.20, 1.55), (2.75, 4.70)],
    18: [(0.20, 2.10), (3.00, 4.70)],
    23: [(0.20, 1.05), (3.10, 4.70)],
    25: [(0.20, 2.25), (3.15, 4.70)],
}


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def category(section: str) -> str:
    if "Bridge" in section:
        return "bridge"
    if "Chorus" in section or section in {"Pre-Chorus", "Beat Pickup"}:
        return "chorus"
    if section == "Intro":
        return "intro"
    if section == "Outro":
        return "outro"
    return "verse"


def cut_length(section: str, ordinal: int) -> float:
    if "Bridge" in section:
        return (3.6, 3.0, 4.0)[ordinal % 3]
    if "Chorus" in section or section in {"Pre-Chorus", "Beat Pickup"}:
        return (1.32, 1.56, 1.20, 1.72)[ordinal % 4]
    if section == "Final Verse":
        return (1.72, 2.10, 1.48)[ordinal % 3]
    if section == "Outro":
        return (1.30, 1.65, 1.15)[ordinal % 3]
    if section == "Intro":
        return (2.20, 1.80)[ordinal % 2]
    return (2.15, 2.55, 1.85)[ordinal % 3]


def choose_source_in(plate: int, duration: float, use_count: int) -> float:
    windows = SAFE_WINDOWS.get(plate, [(0.18, 4.72)])
    valid = [(start, end) for start, end in windows if end - start >= duration]
    if not valid:
        # Long cuts are reserved for stable plates, but retain a safe fallback.
        return 0.18
    start, end = valid[use_count % len(valid)]
    slack = max(0.0, end - start - duration)
    return start + min(slack, (use_count % 3) * 0.22)


def make_edl(shot_plan: Path) -> list[EditItem]:
    with shot_plan.open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["id"][1:]) <= 48]
    pool_cursor = {name: 0 for name in POOLS}
    plate_uses = {number: 0 for number in range(1, 26)}
    items: list[EditItem] = []
    timeline = 0.0
    global_ordinal = 0
    for row in rows:
        section = row["section"]
        group = category(section)
        remaining = float(row["duration"])
        local_ordinal = 0
        while remaining > 0.0005:
            desired = cut_length(section, local_ordinal)
            # Absorb tiny row-end remainders into the preceding cut.  Flash-frame
            # edits read as mistakes, even in a deliberately fast chorus.
            if remaining > desired and remaining - desired < 0.65:
                duration = remaining
            else:
                duration = min(desired, remaining)
            pool = POOLS[group]
            cursor = pool_cursor[group]
            plate_a = pool[cursor % len(pool)]
            pool_cursor[group] += 1
            use_count = plate_uses[plate_a]
            plate_uses[plate_a] += 1
            split = group == "chorus" and global_ordinal % 5 == 3 and duration >= 1.15
            plate_b = pool[(cursor + 2) % len(pool)] if split else None
            source_in = choose_source_in(plate_a, duration, use_count)
            treatment = "split" if split else ("push" if global_ordinal % 3 else "drift")
            items.append(EditItem(
                index=len(items), timeline_in=round(timeline, 6), duration=round(duration, 6),
                section=section, shot_id=row["id"], plate_a=plate_a, plate_b=plate_b,
                source_in=round(source_in, 6), treatment=treatment,
            ))
            timeline += duration
            remaining -= duration
            local_ordinal += 1
            global_ordinal += 1
    if not math.isclose(timeline, PICTURE_DURATION, abs_tol=0.01):
        raise RuntimeError(f"Unexpected picture duration: {timeline}")
    return items


def normal_filter(item: EditItem) -> str:
    common = "eq=contrast=1.045:saturation=1.10:brightness=-0.006,unsharp=5:5:0.32,vignette=PI/5"
    if item.treatment == "drift":
        move = "scale=900:510:flags=lanczos,crop=848:480:x='26+12*sin(0.75*t)':y='15+5*cos(0.6*t)'"
    else:
        move = "scale=910:515:flags=lanczos,crop=848:480:x='31+8*t':y='17+3*sin(t)'"
    opening = item.timeline_in in {0.0, 59.0, 116.14, 205.74}
    flash = ",fade=t=in:st=0:d=0.10:color=white" if opening else ""
    return f"{move},{common}{flash},fps=60,format=yuv420p"


def frame_count(item: EditItem) -> int:
    """Quantize cuts against timeline boundaries so rounding never accumulates."""
    start = round(item.timeline_in * 60)
    end = round((item.timeline_in + item.duration) * 60)
    return end - start


def render_item(item: EditItem, plates: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    source_a = plates / f"plate-{item.plate_a:02d}.mp4"
    frames = frame_count(item)
    render_duration = frames / 60
    base = ["ffmpeg", "-y", "-v", "error", "-ss", f"{item.source_in:.6f}", "-t", f"{render_duration:.6f}", "-i", str(source_a)]
    if item.treatment != "split" or item.plate_b is None:
        run(base + ["-vf", normal_filter(item), "-an", "-frames:v", str(frames),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-pix_fmt", "yuv420p", str(output)])
        return
    source_b = plates / f"plate-{item.plate_b:02d}.mp4"
    second_in = min(4.72 - item.duration, max(0.18, item.source_in + 0.55))
    graph = (
        "[0:v]scale=-2:480:flags=lanczos,crop=424:480:x=(in_w-424)/2[left];"
        "[1:v]scale=-2:480:flags=lanczos,crop=424:480:x=(in_w-424)/2[right];"
        "[left][right]hstack=inputs=2,eq=contrast=1.055:saturation=1.13:brightness=-0.004,"
        "unsharp=5:5:0.34,vignette=PI/5,drawbox=x=421:y=0:w=6:h=480:color=white@0.55:t=fill,"
        "fps=60,format=yuv420p[outv]"
    )
    run(base + ["-ss", f"{second_in:.6f}", "-t", f"{render_duration:.6f}", "-i", str(source_b),
                "-filter_complex", graph, "-map", "[outv]", "-an", "-frames:v", str(frames),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-pix_fmt", "yuv420p", str(output)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("shot_plan", type=Path)
    parser.add_argument("plates", type=Path)
    parser.add_argument("master", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--encode", choices=("x264", "amf"), default="x264")
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    segment_dir = args.output_directory / "segments"
    items = make_edl(args.shot_plan)
    for item in items:
        segment = segment_dir / f"segment-{item.index:03d}.mp4"
        if not segment.is_file():
            print(json.dumps({"render_segment": item.index, "section": item.section, "t": item.timeline_in}), flush=True)
            render_item(item, args.plates, segment)
    black = segment_dir / "segment-black.mp4"
    picture_frames = round(PICTURE_DURATION * 60)
    black_frames = 15050 - picture_frames
    black_duration = black_frames / 60
    if not black.is_file():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={WIDTH}x{HEIGHT}:r=60:d={black_duration:.6f}",
             "-an", "-frames:v", str(black_frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-pix_fmt", "yuv420p", str(black)])
    concat = args.output_directory / "concat.txt"
    concat.write_text("".join(f"file '{(segment_dir / f'segment-{item.index:03d}.mp4').resolve().as_posix()}'\n" for item in items) + f"file '{black.resolve().as_posix()}'\n", encoding="utf-8")
    picture = args.output_directory / "picture-v2-60fps.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(picture)])
    final = args.output_directory / "come-get-your-vitals-full-60fps-v2.mp4"
    encoder = (["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "17", "-qp_p", "19", "-qp_b", "21"]
               if args.encode == "amf" else ["-c:v", "libx264", "-preset", "medium", "-crf", "16"])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(picture), "-i", str(args.master),
         "-filter:v", "scale=1920:1080:flags=lanczos,unsharp=5:5:0.22,fps=60", "-frames:v", "15050",
         "-map", "0:v:0", "-map", "1:a:0", *encoder, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k",
         "-t", f"{FINAL_DURATION:.6f}", "-movflags", "+faststart", str(final)])
    (args.output_directory / "edit-decision-list.json").write_text(json.dumps([asdict(item) for item in items], indent=2), encoding="utf-8")
    print(json.dumps({"complete": str(final), "segments": len(items)}), flush=True)


if __name__ == "__main__":
    main()
