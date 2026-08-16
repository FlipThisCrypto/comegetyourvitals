#!/usr/bin/env python3
"""Generate independent, continuity-chained 40-second editing scenes on two GPUs."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import urllib.request
from pathlib import Path

from flipthis_video_maker.contracts.video_generation import FirstLastFrameGenerationRequest, InterpolationMode
from flipthis_video_maker.media.video_delivery import normalize_interpolated_delivery
from flipthis_video_maker.providers.base.video_generation import ResolvedFirstLastFrameRequest
from flipthis_video_maker.providers.comfyui.wan_flf import MODEL_IDENTITY, ComfyUIWanFirstLastFrameProvider
from flipthis_video_maker.providers.rife.cli import RifeCliInterpolationProvider

from long_scene_contract import (
    DELIVERY_FPS,
    SCENE_FRAMES,
    SEGMENT_SECONDS,
    Scene,
    continuity_steps,
    extract_last_frame,
    load_manifest,
    performance_directive,
    video_matches,
)


WIDTH = 848
HEIGHT = 480
NATIVE_FPS = 8
NEGATIVE = (
    "frozen pose, slideshow, sped-up motion, time lapse, internal cut, camera jump, clipping, intersecting bodies, "
    "duplicate character, extra person, extra limb, missing limb, fused hands, warped hand, warped face, identity drift, "
    "species change, costume change, sudden age change, male singer, masculine lead singer, orca singing, orca lip sync, "
    "orca holding a microphone, teleportation, disappearing prop, unreadable text, logo, watermark"
)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def post_json(url: str, payload: dict[str, object]) -> None:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30):
        pass


def request_for(scene: Scene, beat_index: int, gpu: int, start_asset: str, end_asset: str) -> FirstLastFrameGenerationRequest:
    beat = scene.beats[beat_index]
    provider_id = f"wan22-flf-gpu{gpu}"
    prompt = (
        "One uninterrupted ten-second passage from a polished 3D animated underwater nursing-station scene. "
        f"{beat.prompt} {performance_directive(beat.singing)} "
        "Maintain one continuous timeline with natural-speed movement and coherent weight. Preserve every established character's "
        "face, species, body proportions, uniform, accessories and screen position. Keep hands, fins, tails, hair and props readable. "
        "The orca, whenever present, is a silent background coworker at the vitals workstation: mouth closed, no microphone, no lip sync. "
        "Use continuous camera parallax and environmental motion without any internal edit. Finish exactly in the supplied endpoint composition."
    )
    return FirstLastFrameGenerationRequest(
        provider_id=provider_id,
        provider_model=MODEL_IDENTITY,
        start_frame_asset_id=start_asset,
        target_end_frame_asset_id=end_asset,
        prompt=prompt,
        negative_prompt=NEGATIVE,
        duration_seconds=SEGMENT_SECONDS,
        native_requested_fps=NATIVE_FPS,
        delivery_fps=DELIVERY_FPS,
        width=WIDTH,
        height=HEIGHT,
        aspect_ratio="16:9",
        seed=910_000 + sum(ord(char) for char in scene.scene_id) * 31 + beat_index * 997,
        camera_direction="continuous natural-speed performance camera with coherent parallax",
        interpolation_mode=InterpolationMode.RIFE,
        interpolation_provider_id="rife-local",
        provider_settings={provider_id: {"steps": 24, "cfg": 3.8, "shift": 7.5, "high_noise_end_step": 12}},
    )


async def generate_scene_natives(scene: Scene, gpu: int, args: argparse.Namespace) -> None:
    endpoint = args.endpoint_gpu0 if gpu == 0 else args.endpoint_gpu1
    scene_directory = args.output_directory / scene.scene_id
    scene_directory.mkdir(parents=True, exist_ok=True)
    final = scene_directory / f"{scene.scene_id}-40s-60fps.mp4"
    if video_matches(final, seconds=40):
        print(json.dumps({"resume_scene": scene.scene_id, "gpu": gpu}), flush=True)
        return
    provider = ComfyUIWanFirstLastFrameProvider(
        f"wan22-flf-gpu{gpu}", endpoint=endpoint, workflow_template=args.workflow, gpu_assignment=f"gpu{gpu}"
    )
    health = await provider.health()
    if health.get("ok") is not True:
        raise RuntimeError({"scene": scene.scene_id, "gpu": gpu, "health": health})
    for step in continuity_steps(scene, scene_directory):
        segment_directory = step.continuity_frame.parent
        segment_directory.mkdir(parents=True, exist_ok=True)
        native = segment_directory / "native-8fps.mp4"
        delivery = segment_directory / "delivery-60fps.mp4"
        if not native.is_file() and not video_matches(delivery, seconds=SEGMENT_SECONDS):
            request = request_for(scene, step.index, gpu, f"{scene.scene_id}-{step.index}-start", f"{scene.scene_id}-{step.index}-end")
            await provider.generate(
                ResolvedFirstLastFrameRequest(
                    snapshot=request,
                    start_frame_path=step.start_frame,
                    start_frame_mime_type="image/png",
                    end_frame_path=step.end_frame,
                    end_frame_mime_type="image/png",
                    output_path=native,
                ),
                progress=lambda amount, message, sid=scene.scene_id, idx=step.index: print(json.dumps({
                    "scene": sid, "segment": idx + 1, "gpu": gpu, "progress": round(amount, 4), "stage": message,
                }), flush=True),
            )
        extract_last_frame(native if native.is_file() else delivery, step.continuity_frame)
    print(json.dumps({"scene_natives_complete": scene.scene_id, "gpu": gpu}), flush=True)


async def deliver_scene(scene: Scene, rife: RifeCliInterpolationProvider, args: argparse.Namespace) -> None:
    scene_directory = args.output_directory / scene.scene_id
    final = scene_directory / f"{scene.scene_id}-40s-60fps.mp4"
    if video_matches(final, seconds=40):
        return
    deliveries: list[Path] = []
    report: list[dict[str, object]] = []
    for step in continuity_steps(scene, scene_directory):
        beat = scene.beats[step.index]
        segment_directory = step.continuity_frame.parent
        native = segment_directory / "native-8fps.mp4"
        delivery = segment_directory / "delivery-60fps.mp4"
        if not video_matches(delivery, seconds=SEGMENT_SECONDS):
            interpolated = segment_directory / "interpolated-fullspeed-60fps.mp4"
            await rife.process(native, interpolated, target_fps=DELIVERY_FPS)
            normalize_interpolated_delivery(
                interpolated, delivery, duration_seconds=SEGMENT_SECONDS, delivery_fps=DELIVERY_FPS
            )
        if not video_matches(delivery, seconds=SEGMENT_SECONDS):
            raise RuntimeError(f"Invalid delivery timing: {delivery}")
        deliveries.append(delivery)
        report.append({
            "segment": step.index + 1,
            "start_frame": str(step.start_frame),
            "end_anchor": str(step.end_frame),
            "continuity_frame": str(step.continuity_frame),
            "singing": beat.singing,
            "delivery": str(delivery),
        })
    concat = scene_directory / "concat.txt"
    concat.write_text("".join(f"file '{path.resolve().as_posix()}'\n" for path in deliveries), encoding="utf-8")
    temporary = scene_directory / f".{scene.scene_id}-assembling.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(temporary)])
    temporary.replace(final)
    if not video_matches(final, seconds=40) or int(json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "json", str(final)
    ]))["streams"][0]["nb_frames"]) != SCENE_FRAMES:
        raise RuntimeError(f"Scene failed the 40-second/2400-frame contract: {final}")
    (scene_directory / "scene-report.json").write_text(json.dumps({"scene": scene.scene_id, "segments": report}, indent=2), encoding="utf-8")
    print(json.dumps({"scene_complete": scene.scene_id, "gpu": gpu, "output": str(final)}), flush=True)


async def worker(gpu: int, queue: asyncio.Queue[Scene | None], args: argparse.Namespace) -> None:
    while True:
        scene = await queue.get()
        try:
            if scene is None:
                return
            await generate_scene_natives(scene, gpu, args)
        finally:
            queue.task_done()


async def execute(args: argparse.Namespace) -> None:
    scenes = load_manifest(args.manifest)
    for scene in scenes:
        for frame in (scene.start_frame, *(beat.end_frame for beat in scene.beats)):
            if not frame.is_file():
                raise FileNotFoundError(frame)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    queue: asyncio.Queue[Scene | None] = asyncio.Queue()
    for scene in scenes:
        queue.put_nowait(scene)
    queue.put_nowait(None)
    queue.put_nowait(None)
    await asyncio.gather(worker(0, queue, args), worker(1, queue, args))
    for endpoint in (args.endpoint_gpu0, args.endpoint_gpu1):
        try:
            post_json(endpoint.rstrip("/") + "/free", {"unload_models": True, "free_memory": True})
        except Exception as error:
            print(json.dumps({"warning": "unable to unload Wan model", "endpoint": endpoint, "error": str(error)}), flush=True)
    rife = RifeCliInterpolationProvider(
        args.rife_runtime / ".venv/bin/python", args.rife_runtime / "inference_video.py", args.rife_runtime / "train_log",
        timeout_seconds=1800,
    )
    for scene in scenes:
        await deliver_scene(scene, rife, args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--rife-runtime", type=Path, required=True)
    parser.add_argument("--endpoint-gpu0", default="http://127.0.0.1:8190")
    parser.add_argument("--endpoint-gpu1", default="http://127.0.0.1:8189")
    args = parser.parse_args()
    asyncio.run(execute(args))


if __name__ == "__main__":
    main()
