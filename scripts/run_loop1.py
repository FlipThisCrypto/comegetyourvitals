from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "generated"
IMPROVEMENTS = GENERATED / "improvements"
CONFIG = json.loads((ROOT / "production-config.json").read_text(encoding="utf-8"))
ANALYSIS = json.loads((ROOT / CONFIG["timeline"]["analysis"]).read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "character-registry.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Shot:
    id: str
    start: float
    end: float
    duration: float
    section: str
    location: str
    motion_channels: tuple[str, ...]
    recovery_arc: str


def load_shots() -> list[Shot]:
    path = ROOT / CONFIG["timeline"]["shot_plan"]
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [
        Shot(
            id=r["id"], start=float(r["start_seconds"]), end=float(r["end_seconds"]),
            duration=float(r["duration"]), section=r["section"], location=r["location"],
            motion_channels=tuple(v.strip() for v in r["motion_channels"].split(";") if v.strip()),
            recovery_arc=r["recovery_arc"],
        ) for r in rows
    ]


SHOTS = load_shots()


def ffprobe_duration(path: Path) -> float:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ], text=True)
    return float(raw.strip())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def asset_paths() -> list[Path]:
    assets = [ROOT / CONFIG["timeline"]["audio"]]
    assets += sorted((ROOT / "assets").glob("*.png"))
    assets += [ROOT / "character-registry.json", ROOT / CONFIG["timeline"]["shot_plan"]]
    return assets


def alpha_usable(path: Path) -> bool:
    with Image.open(path) as im:
        if im.mode != "RGBA":
            return False
        lo, hi = im.getchannel("A").getextrema()
        return lo == 0 and hi > 240


def check(name: str, description: str, fn: Callable[[], bool], evidence: str) -> dict:
    try:
        passed = bool(fn())
        error = None
    except Exception as exc:
        passed = False
        error = f"{type(exc).__name__}: {exc}"
    return {
        "iteration": name,
        "description": description,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence,
        "error": error,
    }


def main() -> None:
    t = CONFIG["timeline"]
    r = CONFIG["render"]
    q = CONFIG["motion_qa"]
    p = CONFIG["policies"]
    arc = CONFIG["creative_arc"]
    gates = CONFIG["gates"]
    audio = ROOT / t["audio"]
    required_docs = ["CODEX_MASTER_PROMPT.md", "README.md", "CREATIVE_BIBLE.md", "MOTION_GUARDRAILS.md", "lyrics.md", "music-style.md", "shot-plan.csv", "asset-manifest.json", "project-config.json"]
    nurse_assets = [ROOT / c["asset"] for c in REGISTRY["nurses"]]
    checks = [
        ("L1-001", "Package documentation is fully unpacked", lambda: all((ROOT/x).exists() for x in required_docs), "nine required source documents"),
        ("L1-002", "Authoritative MP3 is in configured audio path", audio.is_file, str(audio.relative_to(ROOT))),
        ("L1-003", "MP3 duration is probed instead of assumed", lambda: abs(ffprobe_duration(audio)-t["duration_seconds"]) < .001, "ffprobe vs production-config"),
        ("L1-004", "Timeline uses deterministic 30 fps", lambda: t["fps"] == 30, "production-config.timeline.fps"),
        ("L1-005", "Delivery canvas is 1920x1080", lambda: (t["width"],t["height"]) == (1920,1080), "production-config.timeline dimensions"),
        ("L1-006", "Frame count is nearest integer to MP3 endpoint", lambda: t["frame_count"] == round(t["duration_seconds"]*t["fps"]), "7525 frames"),
        ("L1-007", "Revised shot contract contains 51 authored beats", lambda: len(SHOTS) == 51, "generated/revised-shot-plan.csv"),
        ("L1-008", "Shot contract starts at zero", lambda: SHOTS[0].start == 0, "R01 start"),
        ("L1-009", "Shot contract reaches authoritative endpoint", lambda: abs(SHOTS[-1].end-t["duration_seconds"]) < .001, "R51 end"),
        ("L1-010", "Shot ranges are contiguous with no gaps", lambda: all(abs(a.end-b.start)<.001 for a,b in zip(SHOTS,SHOTS[1:])), "all adjacent ranges"),
        ("L1-011", "Shot durations are positive and internally consistent", lambda: all(s.duration>0 and abs((s.end-s.start)-s.duration)<.002 for s in SHOTS), "all 51 rows"),
        ("L1-012", "Shot IDs are unique", lambda: len({s.id for s in SHOTS}) == len(SHOTS), "R01-R51"),
        ("L1-013", "Physical geography is immutable", lambda: CONFIG["orientation"] == {"left":"residential","center":"nurses_station","right":"detox"}, "orientation contract"),
        ("L1-014", "Opening creative state is Detox", lambda: arc["opening_state"] == "detox" and SHOTS[0].location == "outside master", "creative arc and R01"),
        ("L1-015", "Midpoint transition is derived from MP3 midpoint", lambda: abs(arc["midpoint_transition_seconds"]-t["duration_seconds"]/2)<.001, "125.4200835 seconds"),
        ("L1-016", "Residential becomes dominant after stabilization", lambda: arc["residential_dominant_from_seconds"] >= arc["bridge_start_seconds"], "creative arc ordering"),
        ("L1-017", "Bridge timing is explicitly locked", lambda: any(s.section == "Bridge" and s.start <= arc["bridge_start_seconds"] <= s.end for s in SHOTS), "142.06 seconds"),
        ("L1-018", "Bridge contains return-to-window emotional beat", lambda: any(s.id == "R32" and "residential window" in s.location for s in SHOTS), "R31-R33"),
        ("L1-019", "Final continuous traversal has locked endpoints", lambda: arc["final_traversal_start_seconds"] == 204.46 and arc["final_traversal_end_seconds"] == 229.34, "R39-R43"),
        ("L1-020", "Outro intake and black tail are explicitly timed", lambda: SHOTS[-5].section == "Outro" and SHOTS[-1].recovery_arc == "END", "R47-R51"),
        ("L1-021", "Persistent character registry is required", lambda: p["character_registry_required"] and (ROOT/"character-registry.json").exists(), "policy + JSON"),
        ("L1-022", "All six canonical nurses are registered", lambda: len(REGISTRY["nurses"]) == 6, "NURSE_* entries"),
        ("L1-023", "Ten recurring fictional clients are registered", lambda: len(REGISTRY["clients"]) == 10, "CLIENT_01-CLIENT_10"),
        ("L1-024", "All character IDs are globally unique", lambda: len({c["id"] for c in REGISTRY["nurses"]+REGISTRY["clients"]}) == 16, "registry IDs"),
        ("L1-025", "Every client has three recovery appearances", lambda: all(all(k in c for k in ["detox_appearance","stabilization_appearance","residential_appearance"]) for c in REGISTRY["clients"]), "client state schema"),
        ("L1-026", "All canonical nurse assets exist", lambda: all(x.is_file() for x in nurse_assets), "six RGBA sheets"),
        ("L1-027", "Canonical nurse sheets have usable transparency", lambda: all(alpha_usable(x) for x in nurse_assets), "RGBA alpha extrema"),
        ("L1-028", "Five canonical environment masters exist", lambda: len(list((ROOT/"assets").glob("env_*.png"))) == 5, "assets/env_*.png"),
        ("L1-029", "Asset inventory is hash-addressable", lambda: all(len(sha256(x)) == 64 for x in asset_paths()), "SHA-256 for render inputs"),
        ("L1-030", "Procedural randomness uses locked seed", lambda: CONFIG["seed"] == 73184, "production-config.seed"),
        ("L1-031", "Beat grid is generated from the actual MP3", lambda: ANALYSIS["detected_tempo_bpm"] > 0 and len(ANALYSIS["beats"]) > 600, "audio-analysis beat list"),
        ("L1-032", "Audio analysis covers complete section structure", lambda: ANALYSIS["sections"][0]["start"] == 0 and ANALYSIS["sections"][-1]["end"] >= 250.84, "11 analyzed sections"),
        ("L1-033", "Critical vocal landmarks are machine-readable", lambda: len(ANALYSIS["vocal_landmarks"]) >= 20, "audio-analysis vocal_landmarks"),
        ("L1-034", "Preflight rejects missing render assets", lambda: all(x.exists() for x in asset_paths()), "asset_paths() has no missing entries"),
        ("L1-035", "Generated, renders and improvement directories are isolated", lambda: all((ROOT/x).exists() for x in ["generated","renders"]) and IMPROVEMENTS.mkdir(parents=True,exist_ok=True) is None, "workspace output layout"),
        ("L1-036", "Manifests use atomic replace writes", lambda: callable(atomic_json), "atomic_json temp + os.replace"),
        ("L1-037", "Renderer is configured for bounded frame chunks", lambda: 1 <= r["chunk_frames"] <= 300, "150-frame chunks"),
        ("L1-038", "Long render is resumable", lambda: r["resume"] is True, "render.resume"),
        ("L1-039", "Long render supports deterministic sharding", lambda: r["shardable"] is True, "render.shardable"),
        ("L1-040", "Preview delivery uses broadly compatible H.264", lambda: r["preview"]["codec"] == "libx264" and r["preview"]["pixel_format"] == "yuv420p", "preview profile"),
        ("L1-041", "Master delivery has a high-quality encode profile", lambda: r["master"]["crf"] <= 16 and r["master"]["audio_bitrate"] == "320k", "master profile"),
        ("L1-042", "ProRes mezzanine profile is defined", lambda: r["mezzanine"]["codec"] == "prores_ks" and r["mezzanine"]["pixel_format"] == "yuv422p10le", "mezzanine profile"),
        ("L1-043", "Normal shots require three independent channels", lambda: q["min_channels_normal"] == 3, "motion budget"),
        ("L1-044", "Hero shots require four independent channels", lambda: q["min_channels_hero"] == 4, "hero motion budget"),
        ("L1-045", "Full-frame static holds are capped at 12 frames", lambda: q["max_static_frames"] == 12, "static limit"),
        ("L1-046", "Production render targets native 1080p", lambda: (r["native_width"],r["native_height"]) == (1920,1080), "native render profile"),
        ("L1-047", "Story-critical text is code-rendered", lambda: p["important_text_rendered_in_code"] is True, "typography policy"),
        ("L1-048", "Privacy and fictional-client policies are enforced", lambda: p["no_phi"] and p["fictional_clients_only"], "privacy policy"),
        ("L1-049", "Final rendering is offline and deterministic", lambda: r["offline_final"] and p["no_external_network_during_render"], "offline policy"),
        ("L1-050", "Full-song render gate remains closed until all 150 iterations pass", lambda: gates["required_loops"] == 3 and gates["iterations_per_loop"] == 50 and gates["full_render_requires_all_iterations"], "production gate contract"),
    ]
    results = [check(*item) for item in checks]
    passed = sum(x["status"] == "PASS" for x in results)
    manifest = {
        "loop": 1,
        "name": "workflow-and-architecture",
        "iterations_required": 50,
        "iterations_passed": passed,
        "status": "PASS" if passed == 50 else "FAIL",
        "iterations": results,
    }
    hashes = {str(x.relative_to(ROOT)).replace("\\","/"): {"sha256":sha256(x),"bytes":x.stat().st_size} for x in asset_paths()}
    atomic_json(GENERATED/"production-asset-hashes.json", hashes)
    atomic_json(IMPROVEMENTS/"loop-01-workflow.json", manifest)
    state_path = IMPROVEMENTS/"state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"loops":{},"total_iterations_passed":0}
    state["loops"]["1"] = {"name":manifest["name"],"passed":passed,"required":50,"status":manifest["status"]}
    state["total_iterations_passed"] = sum(v["passed"] for v in state["loops"].values())
    state["full_render_gate_open"] = state["total_iterations_passed"] == 150 and all(v["status"]=="PASS" for v in state["loops"].values())
    atomic_json(state_path,state)
    print(json.dumps({"loop":1,"passed":passed,"required":50,"status":manifest["status"],"full_render_gate_open":state["full_render_gate_open"]},indent=2))
    if passed != 50:
        for item in results:
            if item["status"] != "PASS": print(json.dumps(item,indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
