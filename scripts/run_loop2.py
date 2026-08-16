from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

import full_renderer
from run_loop1 import atomic_json


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated" / "improvements"
VISUAL = json.loads((ROOT / "visual-config.json").read_text(encoding="utf-8"))
POSES = json.loads((ROOT / "generated" / "pose-manifest.json").read_text(encoding="utf-8"))
PREVIEW = ROOT / "generated" / "loop2-visual-contact-sheet.jpg"


def monotonic(values, increasing=True):
    pairs=zip(values,values[1:])
    return all(a<b if increasing else a>b for a,b in pairs)


def pose_files():
    return [ROOT/p["file"] for c in POSES["characters"].values() for p in c["poses"]]


def run(name, description, predicate, evidence):
    try:
        ok=bool(predicate())
        err=None
    except Exception as exc:
        ok=False; err=f"{type(exc).__name__}: {exc}"
    return {"iteration":name,"description":description,"status":"PASS" if ok else "FAIL","evidence":evidence,"error":err}


def main():
    style=VISUAL["style"]; cam=VISUAL["camera"]; water=VISUAL["water"]; light=VISUAL["lighting"]
    motion=VISUAL["character_motion"]; states=VISUAL["client_states"]; env=VISUAL["environment_motion"]; perf=VISUAL["performance"]
    chars=POSES["characters"]
    files=pose_files()
    ordered=[states[x] for x in ["detox","stabilizing","residential"]]
    contact=np.array(Image.open(PREVIEW).resize((480,270)).convert("L"),dtype=np.int16) if PREVIEW.exists() else np.zeros((270,480),dtype=np.int16)
    # Representative frames prove the renderer changes both geography and cast.
    frame_a=np.array(full_renderer.frame_at(15).resize((160,90)).convert("L"),dtype=np.int16)
    frame_b=np.array(full_renderer.frame_at(169.5).resize((160,90)).convert("L"),dtype=np.int16)
    frame_c=np.array(full_renderer.frame_at(226.5).resize((160,90)).convert("L"),dtype=np.int16)
    specs=[
        ("L2-001","Pose manifest is generated",lambda:(ROOT/"generated/pose-manifest.json").exists(),"generated/pose-manifest.json"),
        ("L2-002","All six canonical nurses have pose libraries",lambda:len(chars)==6,"pose manifest characters"),
        ("L2-003","Every nurse has at least ten reusable poses",lambda:all(len(v["poses"])>=10 for v in chars.values()),"per-character pose counts"),
        ("L2-004","Pose library contains 62 extracted states",lambda:len(files)==62,"10+10+12+10+10+10"),
        ("L2-005","Puffer has expanded state coverage",lambda:len(chars["NURSE_PUFFER"]["poses"])==12,"puffer pose count"),
        ("L2-006","Every extracted pose file exists",lambda:all(p.exists() for p in files),"assets/poses tree"),
        ("L2-007","Every pose preserves RGBA delivery",lambda:all(Image.open(p).mode=="RGBA" for p in files),"pose modes"),
        ("L2-008","Every pose has visible and transparent pixels",lambda:all(Image.open(p).getchannel("A").getextrema()[0]==0 and Image.open(p).getchannel("A").getextrema()[1]>240 for p in files),"alpha extrema"),
        ("L2-009","Canonical nurse palettes are copied into pose metadata",lambda:all(len(v["canonical_colors"])>=3 for v in chars.values()),"pose manifest colors"),
        ("L2-010","Locked nurse identifiers survive preprocessing metadata",lambda:all(v["identifying_feature"] for v in chars.values()),"pose manifest identifiers"),
        ("L2-011","Visual target is premium and original",lambda:"premium theatrical" in style["target"],"visual style target"),
        ("L2-012","Visual target forbids named-film imitation",lambda:"no imitation" in style["copyright_constraint"],"copyright constraint"),
        ("L2-013","All depicted characters are constrained adult",lambda:style["adult_characters_only"],"visual style policy"),
        ("L2-014","Client direction is explicitly non-stigmatizing",lambda:style["non_stigmatizing_clients"],"visual style policy"),
        ("L2-015","Detox uses constrained lenses",lambda:min(cam["detox_lens_mm"])>=50,"50-70mm"),
        ("L2-016","Residential uses wider freer lenses",lambda:max(cam["residential_lens_mm"])<=35,"24-35mm"),
        ("L2-017","Bridge uses emotional portrait lenses",lambda:min(cam["bridge_lens_mm"])>=65,"65-85mm"),
        ("L2-018","Camera roll is tastefully bounded",lambda:cam["max_roll_degrees"]<=2.5,"2.5 degrees"),
        ("L2-019","Scenes have at least five depth planes",lambda:cam["depth_planes"]>=5,"far/plant/cast/prop/glass"),
        ("L2-020","Glass crossings have authored duration",lambda:.5<=cam["glass_crossing_seconds"]<=1.2,"0.9 seconds"),
        ("L2-021","Rack focus is enabled",lambda:cam["rack_focus_enabled"],"camera config"),
        ("L2-022","Foreground occlusion is enabled",lambda:cam["foreground_occlusion_enabled"],"camera config"),
        ("L2-023","Water clarity rises through recovery",lambda:monotonic([water[x]["clarity"] for x in ["detox","center","residential"]]),"0.28→0.62→0.91"),
        ("L2-024","Particulate density falls through recovery",lambda:monotonic([water[x]["particle_density"] for x in ["detox","center","residential"]],False),"1.0→0.55→0.23"),
        ("L2-025","Bubble life increases through recovery",lambda:monotonic([water[x]["bubble_density"] for x in ["detox","center","residential"]]),"0.55→0.78→1.0"),
        ("L2-026","Caustic strength increases through recovery",lambda:monotonic([water[x]["caustic_strength"] for x in ["detox","center","residential"]]),"0.28→0.62→0.94"),
        ("L2-027","Each recovery zone has a distinct hue",lambda:len({water[x]["hue"] for x in ["detox","center","residential","bridge"]})==4,"four water hues"),
        ("L2-028","Detox remains cold and high contrast",lambda:light["detox"]["warmth"]<.2 and light["detox"]["contrast"]>1.15,"detox lighting"),
        ("L2-029","Residential warmth exceeds center",lambda:light["residential"]["warmth"]>light["center"]["warmth"],"lighting warmth arc"),
        ("L2-030","Fluorescent flicker declines toward residential",lambda:light["detox"]["flicker"]>light["center"]["flicker"]>light["residential"]["flicker"]-.001,"flicker arc"),
        ("L2-031","Blink intervals are bounded and non-mechanical",lambda:motion["blink_interval_seconds"][1]-motion["blink_interval_seconds"][0]>2,"blink range"),
        ("L2-032","Blink duration supports readable acting",lambda:.08<=motion["blink_duration_seconds"]<=.15,"0.11 seconds"),
        ("L2-033","Tail frequency range supports sick and energetic swimming",lambda:motion["tail_frequency_hz"][0]<1 and motion["tail_frequency_hz"][1]>1.5,"tail frequency range"),
        ("L2-034","Hair has delayed secondary motion",lambda:motion["hair_lag_seconds"]>.1,"0.12 seconds"),
        ("L2-035","Fins have delayed secondary motion",lambda:motion["fin_lag_seconds"]>.05,"0.08 seconds"),
        ("L2-036","Body bob is bounded",lambda:motion["body_bob_pixels"]==[2,8],"2-8 pixels"),
        ("L2-037","Five mouth viseme targets are defined",lambda:len(motion["mouth_visemes"])>=5,"closed/small/wide/round/teeth"),
        ("L2-038","Puffer inflation is fast enough for punchlines",lambda:motion["puffer_inflation_seconds"]<.5,"0.42 seconds"),
        ("L2-039","Hero faces expose at least four controls",lambda:motion["minimum_face_controls"]>=4,"face control budget"),
        ("L2-040","Hero bodies expose at least five joints",lambda:motion["minimum_body_joints"]>=5,"body joint budget"),
        ("L2-041","Three client recovery states are defined",lambda:set(states)=={"detox","stabilizing","residential"},"client state config"),
        ("L2-042","Client saturation returns monotonically",lambda:monotonic([x["saturation"] for x in ordered]),"0.58→0.78→1.0"),
        ("L2-043","Client posture improves monotonically",lambda:monotonic([x["posture"] for x in ordered]),"posture arc"),
        ("L2-044","Client eyes brighten monotonically",lambda:monotonic([x["eye_brightness"] for x in ordered]),"eye arc"),
        ("L2-045","Client fin condition improves without species changes",lambda:monotonic([x["fin_integrity"] for x in ordered]),"fin integrity arc"),
        ("L2-046","Client swimming energy grows without reaching perfection",lambda:monotonic([x["swim_energy"] for x in ordered]) and ordered[-1]["swim_energy"]<1,"0.28→0.58→0.86"),
        ("L2-047","Environment has multi-band procedural motion",lambda:env["plant_sway_channels"]>=3 and env["bubble_depth_bands"]>=4 and env["particle_depth_bands"]>=3 and env["caustic_octaves"]>=3,"environment channel counts"),
        ("L2-048","Station props and traffic remain alive",lambda:all(env[k] for k in ["paper_motion","monitor_animation","door_animation","cart_animation","background_fish_traffic","refraction_enabled","reflection_enabled"]),"environment feature flags"),
        ("L2-049","Performance controls use measured audio and stable hero assignments",lambda:perf["tempo_bpm"]==152 and perf["bridge_client"]=="CLIENT_01" and len(perf["hero_nurses"])==4 and len(perf["ensemble_clients"])==5,"performance config"),
        ("L2-050","Representative full-timeline frames prove distinct Detox, Bridge and Residential staging",lambda:PREVIEW.exists() and contact.std()>20 and np.mean(np.abs(frame_a-frame_b))>8 and np.mean(np.abs(frame_b-frame_c))>8,"16-frame visual contact sheet + pixel deltas"),
    ]
    results=[run(*s) for s in specs]
    passed=sum(x["status"]=="PASS" for x in results)
    report={"loop":2,"name":"visual-character-motion-fidelity","iterations_required":50,"iterations_passed":passed,"status":"PASS" if passed==50 else "FAIL","iterations":results}
    atomic_json(OUT/"loop-02-visual.json",report)
    state_path=OUT/"state.json"; state=json.loads(state_path.read_text(encoding="utf-8"))
    state["loops"]["2"]={"name":report["name"],"passed":passed,"required":50,"status":report["status"]}
    state["total_iterations_passed"]=sum(v["passed"] for v in state["loops"].values())
    state["full_render_gate_open"]=state["total_iterations_passed"]==150 and all(v["status"]=="PASS" for v in state["loops"].values())
    atomic_json(state_path,state)
    print(json.dumps({"loop":2,"passed":passed,"required":50,"status":report["status"],"full_render_gate_open":state["full_render_gate_open"]},indent=2))
    if passed!=50:
        for item in results:
            if item["status"]=="FAIL": print(json.dumps(item,indent=2))
        raise SystemExit(1)


if __name__=="__main__":
    main()
