#!/usr/bin/env python3
"""Render one distinct-endpoint Wan 2.2 shot and deliver it at 60 fps."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from flipthis_video_maker.contracts.video_generation import FirstLastFrameGenerationRequest, InterpolationMode
from flipthis_video_maker.media.ffmpeg import run
from flipthis_video_maker.media.video_delivery import normalize_interpolated_delivery
from flipthis_video_maker.providers.base.video_generation import ResolvedFirstLastFrameRequest
from flipthis_video_maker.providers.comfyui.wan_flf import MODEL_IDENTITY, ComfyUIWanFirstLastFrameProvider
from flipthis_video_maker.providers.rife.cli import RifeCliInterpolationProvider


NEGATIVE = (
    "still image, frozen pose, low motion, slideshow, pasted character, sticker edge, clipping, "
    "intersecting bodies, duplicate character, extra limb, fused hands, warped face, identity change, "
    "species change, costume change, male singer, orca singing, orca lip sync, orca holding a microphone, "
    "teleportation, text, logo, watermark"
)


async def execute(args: argparse.Namespace) -> None:
    args.output_directory.mkdir(parents=True, exist_ok=False)
    request = FirstLastFrameGenerationRequest(
        provider_id="wan22-flf-gpu1",
        provider_model=MODEL_IDENTITY,
        start_frame_asset_id="cgyv-active-start",
        target_end_frame_asset_id="cgyv-active-end",
        prompt=args.prompt_file.read_text(encoding="utf-8").strip(),
        negative_prompt=NEGATIVE,
        duration_seconds=10,
        native_requested_fps=8,
        delivery_fps=60,
        width=848,
        height=480,
        aspect_ratio="16:9",
        seed=args.seed,
        camera_direction="energetic live performance camera with a smooth lateral arc and a quick push on the beat",
        interpolation_mode=InterpolationMode.RIFE,
        interpolation_provider_id="rife-local",
        provider_settings={"wan22-flf-gpu1": {"steps": 20, "cfg": 4.0, "shift": 8.0, "high_noise_end_step": 10}},
    )
    provider = ComfyUIWanFirstLastFrameProvider(
        request.provider_id,
        endpoint=args.endpoint,
        workflow_template=args.workflow,
        gpu_assignment="gpu1",
    )
    health = await provider.health()
    print(json.dumps({"health": health}), flush=True)
    if health.get("ok") is not True:
        raise RuntimeError(health)
    native = args.output_directory / "active-native-8fps.mp4"
    await provider.generate(
        ResolvedFirstLastFrameRequest(
            snapshot=request,
            start_frame_path=args.start,
            start_frame_mime_type="image/png",
            end_frame_path=args.end,
            end_frame_mime_type="image/png",
            output_path=native,
        ),
        progress=lambda amount, message: print(json.dumps({"progress": round(amount, 4), "stage": message}), flush=True),
    )
    rife = RifeCliInterpolationProvider(
        args.rife_runtime / ".venv/bin/python",
        args.rife_runtime / "inference_video.py",
        args.rife_runtime / "train_log",
        timeout_seconds=1800,
    )
    interpolated = args.output_directory / "active-interpolated-60fps.mp4"
    await rife.process(native, interpolated, target_fps=60)
    delivery = args.output_directory / "active-proof-60fps.mp4"
    normalize_interpolated_delivery(interpolated, delivery, duration_seconds=10, delivery_fps=60)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(delivery), "-vf", "fps=1,scale=424:240,tile=5x2", "-frames:v", "1", str(args.output_directory / "contact-sheet.jpg")])
    print(json.dumps({"complete": str(delivery)}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start", type=Path)
    parser.add_argument("end", type=Path)
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8189")
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--rife-runtime", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=680408)
    args = parser.parse_args()
    asyncio.run(execute(args))


if __name__ == "__main__":
    main()
