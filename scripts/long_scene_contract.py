#!/usr/bin/env python3
"""Dependency-free contracts and timing validation for long generated scenes."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


SEGMENT_SECONDS = 10
SEGMENTS_PER_SCENE = 4
DELIVERY_FPS = 60
SCENE_SECONDS = SEGMENT_SECONDS * SEGMENTS_PER_SCENE
SCENE_FRAMES = SCENE_SECONDS * DELIVERY_FPS
SCENE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENERGY_LEVELS = {"restrained", "medium", "high", "maximum"}
CAMERA_MOVES = {"locked_observational", "slow_dolly", "lateral_arc", "performance_orbit", "crane_rise"}


@dataclass(frozen=True)
class Beat:
    prompt: str
    end_frame: Path
    singing: bool
    focus: tuple[str, ...]
    energy: str
    camera_move: str
    motion_channels: tuple[str, ...]
    action_arc: tuple[str, str, str]


@dataclass(frozen=True)
class Scene:
    scene_id: str
    start_frame: Path
    location: str
    cast: tuple[str, ...]
    singer: str | None
    camera_axis: str
    wardrobe_lock: str
    beats: tuple[Beat, ...]


@dataclass(frozen=True)
class ContinuityStep:
    index: int
    start_frame: Path
    end_frame: Path
    continuity_frame: Path


def performance_directive(singing: bool) -> str:
    if singing:
        return (
            "The female lead performs the vocal with controlled mouth shapes and expressive full-body movement. "
            "Only the female lead sings or holds a microphone."
        )
    return (
        "This is a non-singing story and dance passage. No character lip-syncs or holds a microphone; "
        "mouths stay closed or make brief natural non-vocal reactions."
    )


def motion_directive(beat: Beat) -> str:
    energy = {
        "restrained": "a restrained, natural and emotionally readable",
        "medium": "an active, conversational",
        "high": "a high-energy, rhythmic",
        "maximum": "a maximum celebratory",
    }[beat.energy]
    camera = {
        "locked_observational": "a stable observational camera with only subtle breathing drift",
        "slow_dolly": "one continuous slow dolly with coherent foreground and background parallax",
        "lateral_arc": "one controlled lateral arc that never crosses the established camera axis",
        "performance_orbit": "one shallow performance orbit that keeps every face readable",
        "crane_rise": "one smooth low-to-high crane rise with stable horizon and room geometry",
    }[beat.camera_move]
    setup, development, payoff = beat.action_arc
    return (
        f"Sustain motion for all ten seconds at {energy} level with clear weight shifts and readable faces and limbs. During seconds 0-3: {setup}. "
        f"During seconds 3-7: {development}. During seconds 7-10: {payoff}. Use {camera}. "
        f"Keep these independent motion channels active and coherent: {', '.join(beat.motion_channels)}."
    )


def load_character_registry(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    characters = [*payload.get("nurses", []), *payload.get("clients", [])]
    registry = {character["id"]: character for character in characters if isinstance(character.get("id"), str)}
    if not registry:
        raise ValueError("character registry contains no usable characters")
    return registry


def validate_scene_cast(scenes: tuple[Scene, ...], registry: dict[str, dict[str, object]]) -> None:
    for scene in scenes:
        unknown = sorted(set(scene.cast) - registry.keys())
        if unknown:
            raise ValueError(f"scene {scene.scene_id} references unknown cast: {', '.join(unknown)}")


def identity_directive(scene: Scene, registry: dict[str, dict[str, object]]) -> str:
    descriptions = []
    for character_id in scene.cast:
        character = registry[character_id]
        descriptions.append(
            f"{character_id} is the {character.get('species')} with {character.get('identifying_feature')}"
        )
    singer = f"The sole singer is {scene.singer}." if scene.singer else "This scene has no designated singer."
    return (
        f"Identity and staging lock for all four passages: fixed location is {scene.location}; "
        f"the only recurring cast is {'; '.join(descriptions)}. {singer} "
        f"Keep the camera on the {scene.camera_axis} axis. Wardrobe is immutable: {scene.wardrobe_lock}. "
        "Do not add, remove, merge, replace, recolor or change the species of any cast member."
    )


def load_manifest(path: Path) -> tuple[Scene, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("manifest must contain at least one scene")
    root = path.parent
    scenes: list[Scene] = []
    seen: set[str] = set()
    for raw in raw_scenes:
        scene_id = raw.get("scene_id")
        if not isinstance(scene_id, str) or not SCENE_ID.fullmatch(scene_id):
            raise ValueError(f"invalid scene_id: {scene_id!r}")
        if scene_id in seen:
            raise ValueError(f"duplicate scene_id: {scene_id}")
        seen.add(scene_id)
        location = raw.get("location")
        camera_axis = raw.get("camera_axis")
        wardrobe_lock = raw.get("wardrobe_lock")
        raw_cast = raw.get("cast")
        singer = raw.get("singer")
        for label, value in (("location", location), ("camera_axis", camera_axis), ("wardrobe_lock", wardrobe_lock)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"scene {scene_id} requires a non-empty {label}")
        if not isinstance(raw_cast, list) or not raw_cast or not all(isinstance(item, str) and item for item in raw_cast):
            raise ValueError(f"scene {scene_id} requires a non-empty cast list")
        cast = tuple(raw_cast)
        if len(set(cast)) != len(cast):
            raise ValueError(f"scene {scene_id} cast contains duplicates")
        if singer is not None and singer not in cast:
            raise ValueError(f"scene {scene_id} singer must be null or a member of cast")
        if singer == "NURSE_ORCA":
            raise ValueError(f"scene {scene_id} cannot designate NURSE_ORCA as singer")
        raw_beats = raw.get("beats")
        if not isinstance(raw_beats, list) or len(raw_beats) != SEGMENTS_PER_SCENE:
            raise ValueError(f"scene {scene_id} must contain exactly {SEGMENTS_PER_SCENE} beats")
        beats: list[Beat] = []
        for index, raw_beat in enumerate(raw_beats):
            prompt = raw_beat.get("prompt")
            singing = raw_beat.get("singing")
            end_frame = raw_beat.get("end_frame")
            raw_focus = raw_beat.get("focus")
            energy = raw_beat.get("energy")
            camera_move = raw_beat.get("camera_move")
            raw_channels = raw_beat.get("motion_channels")
            raw_arc = raw_beat.get("action_arc")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"scene {scene_id} beat {index} requires a prompt")
            if not isinstance(singing, bool):
                raise ValueError(f"scene {scene_id} beat {index} singing must be boolean")
            if not isinstance(end_frame, str) or not end_frame:
                raise ValueError(f"scene {scene_id} beat {index} requires an end_frame")
            if not isinstance(raw_focus, list) or not raw_focus or not all(item in cast for item in raw_focus):
                raise ValueError(f"scene {scene_id} beat {index} focus must be a non-empty subset of cast")
            if singing and singer is None:
                raise ValueError(f"scene {scene_id} beat {index} sings without a designated singer")
            if energy not in ENERGY_LEVELS:
                raise ValueError(f"scene {scene_id} beat {index} has invalid energy")
            if camera_move not in CAMERA_MOVES:
                raise ValueError(f"scene {scene_id} beat {index} has invalid camera_move")
            if not isinstance(raw_channels, list) or not all(
                isinstance(channel, str) and channel.strip() for channel in raw_channels
            ) or len(set(raw_channels)) < 3:
                raise ValueError(f"scene {scene_id} beat {index} requires at least three unique motion_channels")
            if not isinstance(raw_arc, dict) or any(
                not isinstance(raw_arc.get(stage), str) or not raw_arc[stage].strip()
                for stage in ("setup", "development", "payoff")
            ):
                raise ValueError(f"scene {scene_id} beat {index} requires setup, development and payoff action_arc")
            beats.append(Beat(
                prompt.strip(), (root / end_frame).resolve(), singing, tuple(raw_focus), energy, camera_move,
                tuple(raw_channels), tuple(raw_arc[stage].strip() for stage in ("setup", "development", "payoff")),
            ))
        start_frame = raw.get("start_frame")
        if not isinstance(start_frame, str) or not start_frame:
            raise ValueError(f"scene {scene_id} requires a start_frame")
        scenes.append(Scene(
            scene_id, (root / start_frame).resolve(), location.strip(), cast, singer,
            camera_axis.strip(), wardrobe_lock.strip(), tuple(beats),
        ))
    return tuple(scenes)


def continuity_steps(scene: Scene, scene_directory: Path) -> tuple[ContinuityStep, ...]:
    steps: list[ContinuityStep] = []
    start = scene.start_frame
    for index, beat in enumerate(scene.beats):
        continuity = scene_directory / f"segment-{index + 1:02d}" / "continuity-end.png"
        steps.append(ContinuityStep(index, start, beat.end_frame, continuity))
        start = continuity
    return tuple(steps)


def video_matches(path: Path, *, seconds: int, fps: int = DELIVERY_FPS) -> bool:
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
        frames = int(stream["nb_frames"])
        duration = float(payload["format"]["duration"])
    except (FileNotFoundError, KeyError, ValueError, ZeroDivisionError, subprocess.SubprocessError, json.JSONDecodeError):
        return False
    return (
        abs(actual_fps - fps) < 0.001
        and frames == seconds * fps
        and abs(duration - seconds) <= 1 / fps
    )


def extract_last_frame(video: Path, output: Path) -> None:
    """Decode the actual final frame for use as the next segment boundary."""
    payload = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames", "-of", "json", str(video),
    ]))
    count = int(payload["streams"][0]["nb_frames"])
    if count < 2:
        raise RuntimeError(f"Video has too few frames: {video}")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vf", f"select=eq(n\\,{count - 1})", "-frames:v", "1", str(output),
    ], check=True)
    if not output.is_file():
        raise RuntimeError(f"Unable to extract continuity frame from {video}")
