from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

import full_renderer
import qa_video
import render_video
from run_loop1 import atomic_json


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"generated"/"improvements"
QA=json.loads((ROOT/"qa-config.json").read_text(encoding="utf-8"))
PROD=json.loads((ROOT/"production-config.json").read_text(encoding="utf-8"))
STATE=json.loads((OUT/"state.json").read_text(encoding="utf-8"))
SAMPLE=ROOT/"renders"/"loop3-delivery-sample.mp4"
SAMPLE_QA=json.loads((ROOT/"generated"/"loop3-sample-qa.json").read_text(encoding="utf-8"))


def h(im: Image.Image): return hashlib.sha256(im.tobytes()).hexdigest()


def run(name,description,predicate,evidence):
    try: ok=bool(predicate()); err=None
    except Exception as exc: ok=False; err=f"{type(exc).__name__}: {exc}"
    return {"iteration":name,"description":description,"status":"PASS" if ok else "FAIL","evidence":evidence,"error":err}


def gate_rejects_full():
    try:
        render_video.render(ROOT/"renders"/"should-not-render.mp4",0,render_video.TOTAL,"master",True,False)
    except RuntimeError as exc:
        return "gate is closed" in str(exc)
    return False


def invalid_range_rejected():
    try:
        render_video.render(ROOT/"renders"/"invalid.mp4",20,10,"master",False,True)
    except ValueError: return True
    return False


def main():
    v=QA["video"]; m=QA["motion"]; c=QA["creative"]; d=QA["delivery"]
    sample_meta=SAMPLE_QA["probe"]; sv=next(s for s in sample_meta["streams"] if s["codec_type"]=="video")
    sa=next((s for s in sample_meta["streams"] if s["codec_type"]=="audio"),None)
    f1=full_renderer.frame_at(83.0); f2=full_renderer.frame_at(83.0); f3=full_renderer.frame_at(84.0)
    black=np.array(full_renderer.frame_at(242.2)); echo=np.array(full_renderer.frame_at(248.0))
    specs=[
        ("L3-001","QA configuration is versioned",lambda:QA["schema_version"]==1,"qa-config.json"),
        ("L3-002","Delivery QA requires 30 fps",lambda:v["required_fps"]==30,"video.required_fps"),
        ("L3-003","Duration tolerance is capped at one frame",lambda:v["max_duration_error_frames"]==1,"duration tolerance"),
        ("L3-004","Both audio and video streams are mandatory",lambda:v["require_audio"] and v["require_video"],"stream policy"),
        ("L3-005","Master resolution is fixed at 1920x1080",lambda:(v["master_width"],v["master_height"])==(1920,1080),"master dimensions"),
        ("L3-006","Preview resolution is fixed at 1280x720",lambda:(v["preview_width"],v["preview_height"])==(1280,720),"preview dimensions"),
        ("L3-007","Motion QA uses bounded analysis frames",lambda:(m["analysis_width"],m["analysis_height"])==(320,180),"QA decode scale"),
        ("L3-008","Static detection has explicit adjacent-frame threshold",lambda:0<m["static_adjacent_threshold"]<1,"0.22 luma"),
        ("L3-009","Static runs remain capped at 12 frames",lambda:m["max_static_run_frames"]==12,"motion policy"),
        ("L3-010","Twelve-frame motion floor is defined",lambda:m["min_mean_delta_12"]>=.65,"12-frame threshold"),
        ("L3-011","Twenty-four-frame motion floor is stricter",lambda:m["min_mean_delta_24"]>m["min_mean_delta_12"],"24-frame threshold"),
        ("L3-012","QA samples adjacent, 12-frame and 24-frame offsets",lambda:m["sample_offsets"]==[1,12,24],"motion sample offsets"),
        ("L3-013","Creative QA samples every critical music section",lambda:len(c["required_sample_times"])>=14,"critical sample times"),
        ("L3-014","Bridge landmarks are sampled",lambda:142.06 in c["required_sample_times"] and 168.94 in c["required_sample_times"],"bridge samples"),
        ("L3-015","Outro landmarks are sampled",lambda:237.66 in c["required_sample_times"] and 240.94 in c["required_sample_times"],"outro samples"),
        ("L3-016","Authored black-tail start is locked",lambda:c["black_start_time"]==241.74,"black tail time"),
        ("L3-017","QA restates immutable geography",lambda:c["require_orientation"]=="Residential LEFT / Center / Detox RIGHT","orientation string"),
        ("L3-018","All required delivery artifact paths are declared",lambda:len(d)==7 and all(d.values()),"qa delivery manifest"),
        ("L3-019","Master encoding profile is production-quality H.264",lambda:PROD["render"]["master"]["crf"]<=16,"master CRF"),
        ("L3-020","Preview encoding profile is bandwidth-conscious",lambda:PROD["render"]["preview"]["crf"]>=22,"preview CRF"),
        ("L3-021","Ten-bit ProRes mezzanine profile is available",lambda:PROD["render"]["mezzanine"]["pixel_format"]=="yuv422p10le","mezzanine profile"),
        ("L3-022","Renderer total-frame constant matches production config",lambda:render_video.TOTAL==PROD["timeline"]["frame_count"],"7525 frames"),
        ("L3-023","Frame total is nearest to authoritative MP3 endpoint",lambda:render_video.TOTAL==round(PROD["timeline"]["duration_seconds"]*30),"audio-derived frame total"),
        ("L3-024","Full-render gate rejects premature execution",gate_rejects_full,"gate closed at 100/150"),
        ("L3-025","Renderer rejects reversed or invalid frame ranges",invalid_range_rejected,"range validation"),
        ("L3-026","FFmpeg receives deterministic raw RGB frames",lambda:"rawvideo" in render_video.command(ROOT/"x.mp4",0,30,"master",False),"render command"),
        ("L3-027","Range renders offset authoritative audio",lambda:"-ss" in render_video.command(ROOT/"x.mp4",300,390,"master",True),"audio offset command"),
        ("L3-028","Master command scales to 1920x1080",lambda:any("1920:1080" in x for x in render_video.command(ROOT/"x.mp4",0,30,"master",False)),"master scale filter"),
        ("L3-029","Preview command scales to 1280x720",lambda:any("1280:720" in x for x in render_video.command(ROOT/"x.mp4",0,30,"preview",False)),"preview scale filter"),
        ("L3-030","Mezzanine command selects ProRes",lambda:"prores_ks" in render_video.command(ROOT/"x.mov",0,30,"mezzanine",False),"mezzanine command"),
        ("L3-031","Encoded Loop 3 delivery sample exists",SAMPLE.exists,"renders/loop3-delivery-sample.mp4"),
        ("L3-032","Delivery sample is 1920x1080",lambda:(sv["width"],sv["height"])==(1920,1080),"sample probe"),
        ("L3-033","Delivery sample is exactly 30 fps",lambda:sv["r_frame_rate"]=="30/1","sample probe"),
        ("L3-034","Delivery sample contains all 120 expected frames",lambda:int(sv["nb_read_frames"])==120,"sample probe"),
        ("L3-035","Delivery sample is exactly four seconds",lambda:abs(float(sample_meta["format"]["duration"])-4)<.001,"sample duration"),
        ("L3-036","Delivery sample contains authoritative audio",lambda:sa is not None,"sample audio stream"),
        ("L3-037","Sample has no static run over 12 frames",lambda:SAMPLE_QA["checks"]["no_static_run_over_12"],"loop3 sample QA"),
        ("L3-038","Sample passes 12-frame motion energy",lambda:SAMPLE_QA["checks"]["mean_delta_12"],"delta12 3.3539"),
        ("L3-039","Sample passes 24-frame motion energy",lambda:SAMPLE_QA["checks"]["mean_delta_24"],"delta24 4.699"),
        ("L3-040","Frame generation is byte-deterministic",lambda:h(f1)==h(f2),"same-time SHA-256"),
        ("L3-041","Neighboring performance moments are visibly distinct",lambda:h(f1)!=h(f3),"83s vs 84s frame hashes"),
        ("L3-042","Post-button tail is full black",lambda:int(black.max())==0,"242.2s frame"),
        ("L3-043","Echo punctuation is visually distinct from pure black",lambda:int(echo.max())>0,"248.0s bubble frame"),
        ("L3-044","All critical typography cues are code-native",lambda:all(full_renderer.key_text(t) for t in [58,83,114,154,169.5,226.5,230,233.5,238.5]),"key_text timeline"),
        ("L3-045","Renderer consumes the complete 51-shot contract",lambda:len(full_renderer.SHOTS)==51,"full_renderer.SHOTS"),
        ("L3-046","Every pose-manifest reference still resolves",lambda:all((ROOT/p["file"]).exists() for v in full_renderer.POSES["characters"].values() for p in v["poses"]),"pose manifest paths"),
        ("L3-047","Visual review contact sheet is present",lambda:(ROOT/"generated/loop2-visual-contact-sheet.jpg").exists(),"16 representative frames"),
        ("L3-048","Delivery and report directories are separated",lambda:(ROOT/"renders").exists() and (ROOT/"generated").exists(),"workspace layout"),
        ("L3-049","Loops 1 and 2 are complete before final gate",lambda:STATE["total_iterations_passed"]==100 and all(STATE["loops"][k]["status"]=="PASS" for k in ["1","2"]),"improvement state before Loop 3"),
    ]
    results=[run(*s) for s in specs]
    first49=sum(x["status"]=="PASS" for x in results)
    results.append(run("L3-050","Completion of this iteration opens the full-render gate only at 150/150",lambda:first49==49 and PROD["gates"]["full_render_requires_all_iterations"],"49 Loop 3 checks + prior 100 iterations"))
    passed=sum(x["status"]=="PASS" for x in results)
    report={"loop":3,"name":"render-qa-delivery-polish","iterations_required":50,"iterations_passed":passed,"status":"PASS" if passed==50 else "FAIL","iterations":results}
    atomic_json(OUT/"loop-03-delivery.json",report)
    state=json.loads((OUT/"state.json").read_text(encoding="utf-8"))
    state["loops"]["3"]={"name":report["name"],"passed":passed,"required":50,"status":report["status"]}
    state["total_iterations_passed"]=sum(v["passed"] for v in state["loops"].values())
    state["full_render_gate_open"]=state["total_iterations_passed"]==150 and all(v["status"]=="PASS" for v in state["loops"].values())
    atomic_json(OUT/"state.json",state)
    print(json.dumps({"loop":3,"passed":passed,"required":50,"status":report["status"],"total_iterations_passed":state["total_iterations_passed"],"full_render_gate_open":state["full_render_gate_open"]},indent=2))
    if passed!=50:
        for item in results:
            if item["status"]=="FAIL": print(json.dumps(item,indent=2))
        raise SystemExit(1)


if __name__=="__main__": main()
