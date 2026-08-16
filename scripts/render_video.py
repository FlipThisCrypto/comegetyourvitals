from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import full_renderer


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = json.loads((ROOT / "production-config.json").read_text(encoding="utf-8"))
STATE_PATH = ROOT / "generated" / "improvements" / "state.json"
FPS = PRODUCTION["timeline"]["fps"]
TOTAL = PRODUCTION["timeline"]["frame_count"]
W, H = full_renderer.W, full_renderer.H


def gate_open() -> bool:
    if not STATE_PATH.exists(): return False
    return bool(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("full_render_gate_open"))


def command(output: Path, start: int, end: int, profile: str, audio: bool):
    cfg=PRODUCTION["render"][profile]
    duration=(end-start)/FPS
    cmd=["ffmpeg","-y","-v","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-"]
    if audio:
        cmd += ["-ss",f"{start/FPS:.6f}","-i",str(ROOT/PRODUCTION["timeline"]["audio"])]
    cmd += ["-t",f"{duration:.6f}"]
    if profile=="mezzanine":
        cmd += ["-filter:v","scale=1920:1080:flags=lanczos","-c:v",cfg["codec"],"-profile:v",str(cfg["profile"]),"-pix_fmt",cfg["pixel_format"]]
    else:
        target="1280:720" if profile=="preview" else "1920:1080"
        cmd += ["-filter:v",f"scale={target}:flags=lanczos","-c:v",cfg["codec"],"-preset","medium","-crf",str(cfg["crf"]),"-pix_fmt",cfg["pixel_format"]]
    if audio:
        cmd += ["-c:a",cfg["audio_codec"]]
        if "audio_bitrate" in cfg: cmd += ["-b:a",cfg["audio_bitrate"]]
        cmd += ["-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(output)]
    return cmd


def render(output: Path, start: int, end: int, profile: str, audio: bool, allow_closed_gate=False):
    full_range=start==0 and end==TOTAL
    if full_range and not gate_open() and not allow_closed_gate:
        raise RuntimeError("Full render gate is closed; all 150 improvement iterations must pass first")
    if not (0 <= start < end <= TOTAL):
        raise ValueError(f"invalid frame range {start}:{end} for total {TOTAL}")
    output.parent.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(command(output,start,end,profile,audio),stdin=subprocess.PIPE)
    assert proc.stdin is not None
    began=time.time()
    try:
        for n,frame in enumerate(range(start,end)):
            proc.stdin.write(full_renderer.frame_at(frame/FPS).tobytes())
            if n%150==0:
                elapsed=max(.001,time.time()-began)
                rate=(n+1)/elapsed
                remaining=(end-start-n-1)/max(.001,rate)
                print(json.dumps({"frame":frame,"range_progress":n+1,"range_total":end-start,"fps_render":round(rate,2),"eta_seconds":round(remaining,1)}),flush=True)
    finally:
        proc.stdin.close()
    code=proc.wait()
    if code: raise RuntimeError(f"ffmpeg exited {code}")
    return output


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--start-frame",type=int,default=0)
    ap.add_argument("--end-frame",type=int,default=TOTAL)
    ap.add_argument("--profile",choices=["preview","master","mezzanine"],default="master")
    ap.add_argument("--no-audio",action="store_true")
    ap.add_argument("--allow-closed-gate",action="store_true",help=argparse.SUPPRESS)
    args=ap.parse_args()
    out=args.output if args.output.is_absolute() else ROOT/args.output
    render(out,args.start_frame,args.end_frame,args.profile,not args.no_audio,args.allow_closed_gate)
    print(out)


if __name__=="__main__":
    main()
