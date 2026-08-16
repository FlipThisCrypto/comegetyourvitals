#!/usr/bin/env python3
"""Render and assemble the full CGYV generative performance master at 60 fps."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from flipthis_video_maker.contracts.video_generation import FirstLastFrameGenerationRequest, InterpolationMode
from flipthis_video_maker.media.video_delivery import normalize_interpolated_delivery
from flipthis_video_maker.providers.base.video_generation import ResolvedFirstLastFrameRequest
from flipthis_video_maker.providers.comfyui.wan_flf import MODEL_IDENTITY, ComfyUIWanFirstLastFrameProvider
from flipthis_video_maker.providers.rife.cli import RifeCliInterpolationProvider


WIDTH = 848
HEIGHT = 480
PLATE_COUNT = 25
NEGATIVE = (
    "still image, frozen pose, low motion, slideshow, pasted character, sticker edge, clipping, "
    "intersecting bodies, duplicate character, extra limb, fused hands, warped face, identity change, "
    "species change, costume change, male singer, masculine lead singer, orca singing, orca lip sync, "
    "orca holding a microphone, teleportation, unreadable text, logo, watermark"
)


@dataclass(frozen=True)
class Pair:
    start: str
    end: str
    action: str


PAIRS = (
    Pair("puffer-gag-a.png", "puffer-gag-b.png", "The female puffer nurse performs a frantic pulse-ox search and a fast comic inflation gag while the other nurses dodge and laugh."),
    Pair("betta-a-v2.png", "betta-b.png", "The female blue betta lead sings the fast verse and completes a strong fin-and-body spin with direct audience connection."),
    Pair("clown-a-v2.png", "clown-b.png", "The female clownfish lead sings and springs from a crouched dance step into a joyful kick while the background nurses react."),
    Pair("tang-a-v2.png", "tang-b.png", "The female blue-and-yellow tang lead sings and performs a quick traveling turn with a sharp reach toward camera."),
    Pair("chorus-start.png", "chorus-end-v1.png", "The rainbow-haired female lead sings the chorus while the female background nurses break into a synchronized silly flash-mob dance."),
    Pair("bridge-a.png", "bridge-b-v2.png", "A quiet compassionate exchange unfolds at the residential window with restrained acting, warm light and continuous gentle motion."),
    Pair("chorus-end-v1.png", "final-flashmob-c.png", "The final chorus builds into a maximum-energy flash mob with distinct female fish nurses dancing behind the female lead."),
)


def prompt_for(index: int, pair: Pair) -> str:
    camera = (
        "a smooth lateral arc and a quick push on the beat" if index % 4 == 0 else
        "a fast but controlled dolly across the performers" if index % 4 == 1 else
        "a low-angle live-performance rise with coherent parallax" if index % 4 == 2 else
        "a short energetic orbit that keeps faces readable"
    )
    return (
        "One continuous ten-second shot in a polished 3D animated underwater nursing-station music video. "
        + pair.action + " Every visible female performer breathes, blinks, moves her torso, arms, hair, fins and tail in time with the high-energy song. "
        "Background nurses and adult fish clients cross the depth of the set and react naturally. The female lead shown at the front is the only singer and uses the only microphone. "
        "The orca nurse, whenever visible, is a silent background coworker only: mouth completely closed, never singing, never lip-syncing and never holding a microphone; the orca works the vitals monitor and only nods to the beat. "
        f"Use {camera}. Preserve character identity, species, anatomy, nurse uniforms, room geometry, shared lighting and clear silhouettes while moving continuously from the supplied start pose to the distinct end pose. "
        "Hair, cloth, fins, bubbles, caustic light and foreground coral have coherent follow-through. No internal cuts."
    )


def request_for(index: int, gpu: int, pair: Pair) -> FirstLastFrameGenerationRequest:
    provider_id = f"wan22-flf-gpu{gpu}"
    return FirstLastFrameGenerationRequest(
        provider_id=provider_id,
        provider_model=MODEL_IDENTITY,
        start_frame_asset_id=f"cgyv-full60-{index:02d}-start",
        target_end_frame_asset_id=f"cgyv-full60-{index:02d}-end",
        prompt=prompt_for(index, pair),
        negative_prompt=NEGATIVE,
        duration_seconds=10,
        native_requested_fps=8,
        delivery_fps=60,
        width=WIDTH,
        height=HEIGHT,
        aspect_ratio="16:9",
        seed=681000 + index * 97,
        camera_direction="energetic live performance camera with continuous parallax",
        interpolation_mode=InterpolationMode.RIFE,
        interpolation_provider_id="rife-local",
        provider_settings={provider_id: {"steps": 20, "cfg": 4.0, "shift": 8.0, "high_noise_end_step": 10}},
    )


async def gpu_worker(gpu: int, indices: list[int], args: argparse.Namespace) -> None:
    endpoint = args.endpoint_gpu0 if gpu == 0 else args.endpoint_gpu1
    for index in indices:
        plate_dir = args.output_directory / "plates" / f"plate-{index:02d}"
        plate_dir.mkdir(parents=True, exist_ok=True)
        native = plate_dir / "native-8fps.mp4"
        if native.is_file():
            print(json.dumps({"resume_native": index, "gpu": gpu}), flush=True)
            continue
        pair = PAIRS[(index - 1) % len(PAIRS)]
        start = args.keyframes / pair.start
        end = args.keyframes / pair.end
        if not start.is_file() or not end.is_file():
            raise FileNotFoundError(f"Plate {index} boundary missing: {start} / {end}")
        request = request_for(index, gpu, pair)
        provider = ComfyUIWanFirstLastFrameProvider(
            request.provider_id,
            endpoint=endpoint,
            workflow_template=args.workflow,
            gpu_assignment=f"gpu{gpu}",
        )
        health = await provider.health()
        if health.get("ok") is not True:
            raise RuntimeError({"plate": index, "health": health})
        print(json.dumps({"start_plate": index, "gpu": gpu, "pair": [pair.start, pair.end]}), flush=True)
        await provider.generate(
            ResolvedFirstLastFrameRequest(
                snapshot=request,
                start_frame_path=start,
                start_frame_mime_type="image/png",
                end_frame_path=end,
                end_frame_mime_type="image/png",
                output_path=native,
            ),
            progress=lambda amount, message, idx=index, device=gpu: print(
                json.dumps({"plate": idx, "gpu": device, "progress": round(amount, 4), "stage": message}), flush=True
            ),
        )
        print(json.dumps({"native_complete": index, "gpu": gpu}), flush=True)


def post_json(url: str, payload: dict) -> None:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30):
        pass


async def interpolate_all(args: argparse.Namespace) -> None:
    for endpoint in (args.endpoint_gpu0, args.endpoint_gpu1):
        try:
            post_json(endpoint.rstrip("/") + "/free", {"unload_models": True, "free_memory": True})
        except Exception as error:
            print(json.dumps({"warning": "unable to unload Wan model", "endpoint": endpoint, "error": str(error)}), flush=True)
    rife = RifeCliInterpolationProvider(
        args.rife_runtime / ".venv/bin/python",
        args.rife_runtime / "inference_video.py",
        args.rife_runtime / "train_log",
        timeout_seconds=1800,
    )
    for index in range(1, PLATE_COUNT + 1):
        plate_dir = args.output_directory / "plates" / f"plate-{index:02d}"
        delivery = plate_dir / "delivery-60fps.mp4"
        if delivery_is_valid(delivery):
            print(json.dumps({"resume_delivery": index}), flush=True)
            continue
        native = plate_dir / "native-8fps.mp4"
        interpolated = plate_dir / "interpolated-fullspeed-60fps.mp4"
        await rife.process(native, interpolated, target_fps=60)
        normalize_interpolated_delivery(
            interpolated,
            delivery,
            duration_seconds=10,
            delivery_fps=60,
        )
        if not delivery_is_valid(delivery):
            raise RuntimeError(f"Plate {index} delivery failed the 10-second/600-frame timing contract")
        print(json.dumps({"delivery_complete": index}), flush=True)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def delivery_is_valid(path: Path, *, duration_seconds: float = 10.0, fps: int = 60) -> bool:
    """Reject stale deliveries that have the right filename but the wrong timing."""
    if not path.is_file():
        return False
    try:
        payload = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate,nb_frames:format=duration",
            "-of", "json", str(path),
        ]))
        stream = payload["streams"][0]
        numerator, denominator = (int(value) for value in stream["avg_frame_rate"].split("/"))
        actual_fps = numerator / denominator
        actual_frames = int(stream["nb_frames"])
        actual_duration = float(payload["format"]["duration"])
    except (FileNotFoundError, KeyError, ValueError, ZeroDivisionError, subprocess.SubprocessError, json.JSONDecodeError):
        return False
    expected_frames = round(duration_seconds * fps)
    return (
        abs(actual_fps - fps) < 0.001
        and actual_frames == expected_frames
        and abs(actual_duration - duration_seconds) <= 1 / fps
    )


def assemble(args: argparse.Namespace) -> Path:
    edit_dir = args.output_directory / "edit"
    edit_dir.mkdir(parents=True, exist_ok=True)
    with args.shot_plan.open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["id"][1:]) <= 48]
    pools = {
        "puffer": [1, 8, 15, 22],
        "verse": [2, 3, 4, 9, 10, 11, 16, 17, 18, 23, 24, 25],
        "chorus": [5, 7, 12, 14, 19, 21],
        "bridge": [6, 13, 20],
    }
    pool_counts = {name: 0 for name in pools}
    fragments: list[tuple[dict[str, str], float, int]] = []
    for row in rows:
        remaining = float(row["duration"])
        fragment_index = 0
        while remaining > 0.0005:
            duration = min(4.8, remaining)
            fragments.append((row, duration, fragment_index))
            remaining -= duration
            fragment_index += 1
    segments: list[Path] = []
    for shot_index, (row, duration, fragment_index) in enumerate(fragments):
        if "Bridge" in row["section"]:
            pool_name = "bridge"
        elif "Chorus" in row["section"] or row["section"] == "Pre-Chorus" or row["section"] == "Beat Pickup":
            pool_name = "chorus"
        elif row["section"] in {"Intro", "Outro"} and shot_index % 2 == 0:
            pool_name = "puffer"
        else:
            pool_name = "verse"
        pool = pools[pool_name]
        use_count = pool_counts[pool_name]
        plate_number = pool[use_count % len(pool)]
        pool_counts[pool_name] += 1
        offset = min((use_count % 3) * 0.1, max(0.0, 5.0 - duration))
        source = args.output_directory / "plates" / f"plate-{plate_number:02d}" / "delivery-60fps.mp4"
        segment = edit_dir / f"{row['id']}-{fragment_index:02d}.mp4"
        if not segment.is_file():
            filters = [f"trim=start={offset:.3f}:duration={duration:.3f}", "setpts=PTS-STARTPTS"]
            if "Chorus" in row["section"] and shot_index % 2 == 0:
                filters.append("fade=t=in:st=0:d=0.08:color=white")
            if use_count >= len(pool) and use_count % 2 == 1:
                filters.extend(["crop=800:452:x=24+12*sin(2*PI*t):y=14", "scale=848:480:flags=lanczos"])
            run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vf", ",".join(filters), "-an", "-r", "60", "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", str(segment)])
        segments.append(segment)
    black_duration = 250.84 - sum(float(row["duration"]) for row in rows)
    black = edit_dir / "outro-black.mp4"
    if not black.is_file():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r=60:d={black_duration:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", str(black)])
    concat_list = edit_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{path.as_posix()}'\n" for path in [*segments, black]), encoding="utf-8")
    picture = edit_dir / "picture-60fps.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(picture)])
    final = args.output_directory / "come-get-your-vitals-full-60fps.mp4"
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(picture), "-i", str(args.audio),
        "-filter:v", "scale=1920:1080:flags=lanczos,fps=60", "-frames:v", "15050",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-t", "250.833333", "-movflags", "+faststart", str(final),
    ])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(final), "-vf", "fps=1/12,scale=320:180,tile=5x5", "-frames:v", "1", str(args.output_directory / "contact-sheet.jpg")])
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames", "-of", "json", str(final)]))
    (args.output_directory / "ffprobe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    return final


async def main_async(args: argparse.Namespace) -> None:
    args.output_directory.mkdir(parents=True, exist_ok=True)
    await asyncio.gather(
        gpu_worker(0, list(range(2, PLATE_COUNT + 1, 2)), args),
        gpu_worker(1, list(range(1, PLATE_COUNT + 1, 2)), args),
    )
    await interpolate_all(args)
    final = assemble(args)
    print(json.dumps({"full_master_complete": str(final)}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("keyframes", type=Path)
    parser.add_argument("shot_plan", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--rife-runtime", type=Path, required=True)
    parser.add_argument("--endpoint-gpu0", default="http://127.0.0.1:8190")
    parser.add_argument("--endpoint-gpu1", default="http://127.0.0.1:8189")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
