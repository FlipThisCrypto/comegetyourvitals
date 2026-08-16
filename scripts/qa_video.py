from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np


ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/"qa-config.json").read_text(encoding="utf-8"))


def probe(path: Path):
    raw=subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_entries","stream=index,codec_type,codec_name,width,height,r_frame_rate,duration,nb_read_frames:format=duration","-of","json",str(path)])
    return json.loads(raw)


def decode(path: Path,w=320,h=180):
    raw=subprocess.check_output(["ffmpeg","-v","error","-i",str(path),"-an","-vf",f"scale={w}:{h}","-f","rawvideo","-pix_fmt","gray","-"])
    return np.frombuffer(raw,dtype=np.uint8).reshape((-1,h,w))


def max_run(mask):
    best=cur=0
    for v in mask:
        cur=cur+1 if v else 0; best=max(best,cur)
    return best


def analyze(path: Path,expected_frames: int,expected_duration: float,expected_fps: int=30):
    meta=probe(path); frames=decode(path,CFG["motion"]["analysis_width"],CFG["motion"]["analysis_height"])
    streams=meta["streams"]; video=next(s for s in streams if s["codec_type"]=="video"); audio=next((s for s in streams if s["codec_type"]=="audio"),None)
    f=frames.astype(np.int16)
    adjacent=np.mean(np.abs(f[1:]-f[:-1]),axis=(1,2))
    d12=np.mean(np.abs(f[12:]-f[:-12]),axis=(1,2)) if len(f)>12 else np.array([0.])
    d24=np.mean(np.abs(f[24:]-f[:-24]),axis=(1,2)) if len(f)>24 else np.array([0.])
    static=max_run(adjacent<CFG["motion"]["static_adjacent_threshold"])
    checks={
        "frame_count":len(frames)==expected_frames==int(video["nb_read_frames"]),
        "duration":abs(float(meta["format"]["duration"])-expected_duration)<=1/expected_fps+.001,
        "fps":video["r_frame_rate"]==f"{expected_fps}/1",
        "audio_present":audio is not None,
        "no_static_run_over_0_4_seconds":static<=round(expected_fps*0.4),
        "mean_delta_12":float(np.mean(d12))>=CFG["motion"]["min_mean_delta_12"],
        "mean_delta_24":float(np.mean(d24))>=CFG["motion"]["min_mean_delta_24"],
    }
    return {"file":str(path),"status":"PASS" if all(checks.values()) else "FAIL","checks":checks,"metrics":{"frames":len(frames),"duration":float(meta["format"]["duration"]),"longest_static_run":static,"adjacent_mean":round(float(np.mean(adjacent)),4),"delta12_mean":round(float(np.mean(d12)),4),"delta24_mean":round(float(np.mean(d24)),4)},"probe":meta}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("file",type=Path); ap.add_argument("--frames",type=int,required=True); ap.add_argument("--duration",type=float,required=True); ap.add_argument("--fps",type=int,default=30); ap.add_argument("--out",type=Path)
    a=ap.parse_args(); path=a.file if a.file.is_absolute() else ROOT/a.file
    result=analyze(path,a.frames,a.duration,a.fps)
    if a.out:
        out=a.out if a.out.is_absolute() else ROOT/a.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"status":result["status"],"checks":result["checks"],"metrics":result["metrics"]},indent=2))
    if result["status"]!="PASS": raise SystemExit(1)


if __name__=="__main__": main()
