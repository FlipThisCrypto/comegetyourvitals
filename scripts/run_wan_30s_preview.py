#!/usr/bin/env python3
"""Render a three-shot, 30-second CGYV Wan/RIFE preview with original audio."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from flipthis_video_maker.contracts.video_generation import (
    FirstLastFrameGenerationRequest,
    InterpolationMode,
)
from flipthis_video_maker.media.ffmpeg import run
from flipthis_video_maker.media.video_delivery import (
    inspect_delivery_contract,
    normalize_interpolated_delivery,
    write_qa_report,
)
from flipthis_video_maker.providers.base.video_generation import ResolvedFirstLastFrameRequest
from flipthis_video_maker.providers.comfyui.wan_flf import (
    MODEL_IDENTITY,
    ComfyUIWanFirstLastFrameProvider,
)
from flipthis_video_maker.providers.rife.cli import RifeCliInterpolationProvider


WIDTH = 848
HEIGHT = 480
NEGATIVE = (
    "cut, transition, crossfade, dissolve, morph, slideshow, still image, pasted character, sticker "
    "edge, sliding body, clipping, intersecting bodies, duplicate character, extra person, extra limb, "
    "missing limb, fused hands, warped face, identity change, species change, costume change, teleportation, "
    "frozen motion, male singer, masculine vocal performance, orca singing, orca lip-sync, orca holding "
    "microphone, stethoscope used as microphone, camera shake, text, logo, watermark"
)


@dataclass(frozen=True)
class Shot:
    number: int
    endpoint: str
    gpu_assignment: str
    seed: int
    prompt: str


SHOTS = (
    Shot(
        1,
        "http://127.0.0.1:8189",
        "gpu1",
        39001,
        "A single continuous underwater hospital performance shot during the spoken intro. The rainbow "
        "mermaid RN is the female lead but does not sing at first: mouth at rest, she hears an intake "
        "announcement, turns toward the commotion, and reaches for the missing pulse oximeter. The female "
        "puffer RN searches the counter, reacts with comic frustration, then points toward the hallway. "
        "The orca RN remains a silent background coworker with mouth closed, monitoring the vitals screen "
        "and moving farther from the performers. In only the final second, the rainbow nurse turns to camera "
        "and visibly begins the first sung line. Natural blinks, breathing, hair, tails, bubbles, caustic light, "
        "and background fish. Preserve all identities, anatomy, wardrobe, room geometry and shared lighting. "
        "Locked eye-level camera with subtle human-operated drift; no cut or zoom. Return near the opening pose."
    ),
    Shot(
        2,
        "http://127.0.0.1:8190",
        "gpu0",
        39002,
        "A single continuous underwater hospital live-performance shot. The rainbow mermaid RN is the clear "
        "female lead vocalist and confidently lip-syncs the fast verse into the only microphone, completing "
        "one rhythmic body-and-tail dance phrase with expressive eyes and a direct audience connection. The "
        "female puffer RN performs a quick supporting response, bounces to the beat, and reacts to the lyric. "
        "The orca RN is silent throughout, mouth closed, never lip-syncing, working at the background vitals "
        "monitor and briefly glancing over with a deadpan reaction. Coherent secondary motion in hair, tails, "
        "scrubs, bubbles and caustic light. Preserve identities, anatomy, wardrobe, set and object placement. "
        "Locked eye-level camera with a very gentle performance push; no cut. Return near the opening pose."
    ),
    Shot(
        3,
        "http://127.0.0.1:8189",
        "gpu1",
        39003,
        "A single continuous underwater hospital live-performance shot continuing the female rap verse. The "
        "rainbow mermaid RN remains the only lead vocalist, articulating the lyric into the only microphone, "
        "then punctuating the final line with a sharp hand gesture and confident tail sweep. The female puffer "
        "RN pantomimes a medication negotiation with amused disbelief, briefly puffs, and settles back into "
        "the beat. The orca RN stays silent with mouth closed, checks a radio and vitals display in the rear, "
        "and never performs the vocal. All three react naturally to one another. Hair, fins, tails, bubbles, "
        "scrubs, screens and water light move coherently. Preserve identities, anatomy, wardrobe and room "
        "layout. Locked eye-level camera with restrained live-operator sway; no cut. Return near opening pose."
    ),
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_image", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--rife-runtime", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def make_request(shot: Shot) -> FirstLastFrameGenerationRequest:
    provider_id = f"wan22-flf-{shot.gpu_assignment}"
    return FirstLastFrameGenerationRequest(
        provider_id=provider_id,
        provider_model=MODEL_IDENTITY,
        start_frame_asset_id=f"cgyv-preview-shot-{shot.number}-start",
        target_end_frame_asset_id=f"cgyv-preview-shot-{shot.number}-end",
        prompt=shot.prompt,
        negative_prompt=NEGATIVE,
        duration_seconds=10,
        native_requested_fps=8,
        delivery_fps=60,
        width=WIDTH,
        height=HEIGHT,
        aspect_ratio="16:9",
        seed=shot.seed,
        camera_direction="continuous eye-level performance camera; no cut, pan, whip, or digital zoom",
        interpolation_mode=InterpolationMode.RIFE,
        interpolation_provider_id="rife-local",
        provider_settings={provider_id: {"steps": 20, "cfg": 4.0, "shift": 8.0, "high_noise_end_step": 10}},
    )


async def generate_native(shot: Shot, boundary: Path, root: Path, workflow: Path) -> tuple[Shot, FirstLastFrameGenerationRequest, Path]:
    shot_dir = root / f"shot-{shot.number:02d}"
    shot_dir.mkdir()
    request = make_request(shot)
    provider = ComfyUIWanFirstLastFrameProvider(
        request.provider_id,
        endpoint=shot.endpoint,
        workflow_template=workflow,
        gpu_assignment=shot.gpu_assignment,
    )
    health = await provider.health()
    print(json.dumps({"shot": shot.number, "health": health}), flush=True)
    if health.get("ok") is not True:
        raise RuntimeError(f"Shot {shot.number} endpoint unhealthy: {health}")
    native = shot_dir / "native-8fps.mp4"
    await provider.generate(
        ResolvedFirstLastFrameRequest(
            snapshot=request,
            start_frame_path=boundary,
            start_frame_mime_type="image/png",
            end_frame_path=boundary,
            end_frame_mime_type="image/png",
            output_path=native,
        ),
        progress=lambda amount, message: print(
            json.dumps({"shot": shot.number, "progress": round(amount, 4), "stage": message}), flush=True
        ),
    )
    return shot, request, native


async def postprocess(result: tuple[Shot, FirstLastFrameGenerationRequest, Path], boundary: Path, rife_root: Path) -> Path:
    shot, request, native = result
    shot_dir = native.parent
    rife = RifeCliInterpolationProvider(
        rife_root / ".venv/bin/python",
        rife_root / "inference_video.py",
        rife_root / "train_log",
        timeout_seconds=1800,
    )
    interpolated = shot_dir / "interpolated-60fps.mp4"
    await rife.process(native, interpolated, target_fps=60)
    delivery = shot_dir / "delivery-600.mp4"
    normalize_interpolated_delivery(interpolated, delivery, duration_seconds=10, delivery_fps=60)
    evidence = shot_dir / "evidence"
    qa = inspect_delivery_contract(
        delivery,
        request=request,
        required_start=boundary,
        target_end=boundary,
        evidence_directory=evidence,
    )
    write_qa_report(qa, shot_dir / "qa-report.json")
    print(json.dumps({"shot": shot.number, "technical_qa": qa["passed"]}), flush=True)
    return delivery


def assemble(deliveries: list[Path], audio: Path, output: Path) -> None:
    command = ["ffmpeg", "-y", "-v", "error"]
    for delivery in deliveries:
        command.extend(["-i", str(delivery)])
    command.extend(["-i", str(audio)])
    video_inputs = "".join(f"[{index}:v]" for index in range(len(deliveries)))
    command.extend(
        [
            "-filter_complex",
            f"{video_inputs}concat=n={len(deliveries)}:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            f"{len(deliveries)}:a:0",
            "-t",
            "30",
            "-r",
            "60",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "14",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    subprocess.run(command, check=True)


async def main_async(args: argparse.Namespace) -> None:
    paths = (args.source_image, args.audio, args.output_directory, args.workflow, args.rife_runtime)
    if not all(path.is_absolute() for path in paths):
        raise ValueError("All paths must be absolute")
    if not args.source_image.is_file() or not args.audio.is_file() or not args.workflow.is_file():
        raise FileNotFoundError("Required input is missing")
    if args.output_directory.exists() and not args.resume:
        raise FileExistsError(args.output_directory)
    args.output_directory.mkdir(parents=True, exist_ok=args.resume)
    boundary = args.output_directory / "shared-performance-boundary.png"
    if not boundary.is_file():
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(args.source_image),
                "-vf",
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
                "-frames:v",
                "1",
                str(boundary),
            ]
        )

    if args.resume:
        resumed = []
        for shot in SHOTS:
            native = args.output_directory / f"shot-{shot.number:02d}" / "native-8fps.mp4"
            if not native.is_file():
                raise FileNotFoundError(f"Cannot resume without native shot {shot.number}: {native}")
            resumed.append((shot, make_request(shot), native))
        first, second, third = resumed
        print(json.dumps({"resume": True, "native_shots": [str(item[2]) for item in resumed]}), flush=True)
    else:
        first, second = await asyncio.gather(
            generate_native(SHOTS[0], boundary, args.output_directory, args.workflow),
            generate_native(SHOTS[1], boundary, args.output_directory, args.workflow),
        )
        third = await generate_native(SHOTS[2], boundary, args.output_directory, args.workflow)
    deliveries = []
    for result in (first, second, third):
        deliveries.append(await postprocess(result, boundary, args.rife_runtime))
    final = args.output_directory / "cgyv-first-30s-preview.mp4"
    assemble(deliveries, args.audio, final)
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(final),
            "-vf",
            "fps=2/3,scale=424:240,tile=5x4",
            "-frames:v",
            "1",
            str(args.output_directory / "preview-contact-sheet.jpg"),
        ]
    )
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames",
                "-of",
                "json",
                str(final),
            ],
            text=True,
        )
    )
    (args.output_directory / "preview-ffprobe.json").write_text(json.dumps(probe, indent=2) + "\n")
    print(json.dumps({"status": "COMPLETE", "final": str(final), "probe": probe}, indent=2), flush=True)


def main() -> None:
    asyncio.run(main_async(arguments()))


if __name__ == "__main__":
    main()
