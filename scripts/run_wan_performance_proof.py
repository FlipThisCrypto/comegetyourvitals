#!/usr/bin/env python3
"""Generate and QA a 10-second CGYV performance proof on FlipThisVideoMaker."""

from __future__ import annotations

import argparse
import asyncio
import json
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
from flipthis_video_maker.providers.base.video_generation import (
    ResolvedFirstLastFrameRequest,
)
from flipthis_video_maker.providers.comfyui.wan_flf import (
    MODEL_IDENTITY,
    ComfyUIWanFirstLastFrameProvider,
)
from flipthis_video_maker.providers.rife.cli import RifeCliInterpolationProvider


WIDTH = 848
HEIGHT = 480
PROMPT = (
    "One continuous locked-camera live musical performance in an underwater hospital nurse "
    "station. The rainbow mermaid RN at right is the clearly visible female lead vocalist: she sings "
    "into her microphone, articulates the lyrics, sways her torso and tail through one confident dance "
    "phrase, and reaches toward the audience. The female pufferfish RN in the middle sings a short "
    "supporting response, bounces naturally to the beat, briefly puffs her cheeks and body, then relaxes, "
    "with hair and fins following through. The orca RN is a silent background coworker only: mouth "
    "closed, never singing, never lip-syncing, and never holding a microphone; the orca checks a vitals "
    "monitor, nods to the beat, and reacts supportively before moving farther into the background. The "
    "female performers maintain eye contact, breathe, blink, and react to each other. Hair, tails, "
    "scrubs, bubbles, caustic light, and background fish move coherently. Preserve each exact identity, "
    "species, anatomy, wardrobe, facial features, colors, room layout, lighting, and object placement. "
    "The group returns naturally near the opening pose at the end for a seamless performance loop."
)
NEGATIVE = (
    "cut, edit, transition, crossfade, dissolve, morph, slideshow, still image, pasted character, "
    "sticker edge, sliding body, clipping, intersecting bodies, duplicate character, extra person, "
    "extra limb, missing limb, fused hands, warped face, identity change, costume change, microphone "
    "change, teleportation, frozen motion, camera shake, pan, zoom, male singer, orca singing, orca "
    "lip-sync, orca holding microphone, text, logo, watermark"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("source_image", type=Path)
    result.add_argument("output_directory", type=Path)
    result.add_argument("--endpoint", default="http://127.0.0.1:8189")
    result.add_argument("--workflow", type=Path, required=True)
    result.add_argument("--rife-runtime", type=Path, required=True)
    result.add_argument("--seed", type=int, default=902104)
    return result


def contact_sheet(video: Path, output: Path, *, columns: int = 9) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"fps=1,scale=424:240,tile={columns}x2",
            "-frames:v",
            "1",
            str(output),
        ]
    )


async def execute(args: argparse.Namespace) -> None:
    if not args.source_image.is_file():
        raise FileNotFoundError(args.source_image)
    if args.output_directory.exists():
        raise FileExistsError(args.output_directory)
    args.output_directory.mkdir(parents=True)
    boundary = args.output_directory / "performance-loop-boundary.png"
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
    request = FirstLastFrameGenerationRequest(
        provider_id="wan22-flf-gpu1",
        provider_model=MODEL_IDENTITY,
        start_frame_asset_id="cgyv-performance-start-v1",
        target_end_frame_asset_id="cgyv-performance-loop-end-v1",
        prompt=PROMPT,
        negative_prompt=NEGATIVE,
        duration_seconds=10,
        native_requested_fps=8,
        delivery_fps=60,
        width=WIDTH,
        height=HEIGHT,
        aspect_ratio="16:9",
        seed=args.seed,
        camera_direction="locked eye-level performance camera; no cut, pan, tilt, zoom, or dolly",
        interpolation_mode=InterpolationMode.RIFE,
        interpolation_provider_id="rife-local",
        provider_settings={
            "wan22-flf-gpu1": {
                "steps": 20,
                "cfg": 4.0,
                "shift": 8.0,
                "high_noise_end_step": 10,
            }
        },
    )
    provider = ComfyUIWanFirstLastFrameProvider(
        request.provider_id,
        endpoint=args.endpoint,
        workflow_template=args.workflow,
        gpu_assignment="gpu1",
    )
    health = await provider.health()
    print(json.dumps({"wan_health": health}, indent=2), flush=True)
    if health.get("ok") is not True:
        raise RuntimeError(f"Wan endpoint is unhealthy: {health}")
    native = args.output_directory / "performance-native-8fps.mp4"
    result = await provider.generate(
        ResolvedFirstLastFrameRequest(
            snapshot=request,
            start_frame_path=boundary,
            start_frame_mime_type="image/png",
            end_frame_path=boundary,
            end_frame_mime_type="image/png",
            output_path=native,
        ),
        progress=lambda amount, message: print(
            json.dumps({"progress": round(amount, 4), "stage": message}), flush=True
        ),
    )
    print(json.dumps({"wan_result": result.model_dump(mode="json")}, indent=2), flush=True)
    contact_sheet(native, args.output_directory / "native-contact-sheet.jpg")

    rife = RifeCliInterpolationProvider(
        args.rife_runtime / ".venv/bin/python",
        args.rife_runtime / "inference_video.py",
        args.rife_runtime / "train_log",
        timeout_seconds=1800,
    )
    interpolated = args.output_directory / "performance-interpolated-60fps.mp4"
    await rife.process(native, interpolated, target_fps=60)
    delivery = args.output_directory / "performance-proof-60fps.mp4"
    normalize_interpolated_delivery(
        interpolated,
        delivery,
        duration_seconds=10,
        delivery_fps=60,
    )
    qa = inspect_delivery_contract(
        delivery,
        request=request,
        required_start=boundary,
        target_end=boundary,
        evidence_directory=args.output_directory / "evidence",
    )
    write_qa_report(qa, args.output_directory / "qa-report.json")
    contact_sheet(delivery, args.output_directory / "delivery-contact-sheet.jpg")
    print(json.dumps({"status": "PASS" if qa["passed"] else "FAIL", "qa": qa}, indent=2), flush=True)


def main() -> None:
    args = parser().parse_args()
    if not all(path.is_absolute() for path in (args.source_image, args.output_directory, args.workflow, args.rife_runtime)):
        raise ValueError("All paths must be absolute")
    asyncio.run(execute(args))


if __name__ == "__main__":
    main()
