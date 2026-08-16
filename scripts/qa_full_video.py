from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np


ROOT=Path(__file__).resolve().parents[1]
VIDEO=ROOT/"renders"/"master_1080p.mp4"
FPS=30; EXPECTED=7525; DURATION=EXPECTED/FPS
BLACK_START=241.74; ACTIVE_END=round(BLACK_START*FPS)


def probe(path):
    return json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_entries","stream=index,codec_type,codec_name,width,height,r_frame_rate,duration,nb_read_frames:format=duration,size,bit_rate","-of","json",str(path)]))


def decode_gray(path,w=160,h=90):
    raw=subprocess.check_output(["ffmpeg","-v","error","-i",str(path),"-an","-vf",f"scale={w}:{h}","-f","rawvideo","-pix_fmt","gray","-"])
    return np.frombuffer(raw,dtype=np.uint8).reshape((-1,h,w))


def max_run(mask):
    best=cur=0
    for v in mask:
        cur=cur+1 if v else 0; best=max(best,cur)
    return best


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        while b:=f.read(1024*1024): h.update(b)
    return h.hexdigest()


def main():
    meta=probe(VIDEO); streams=meta["streams"]; video=next(s for s in streams if s["codec_type"]=="video"); audio=next(s for s in streams if s["codec_type"]=="audio")
    frames=decode_gray(VIDEO); f=frames.astype(np.int16); active=f[:ACTIVE_END]
    adjacent=np.mean(np.abs(active[1:]-active[:-1]),axis=(1,2)); d12=np.mean(np.abs(active[12:]-active[:-12]),axis=(1,2)); d24=np.mean(np.abs(active[24:]-active[:-24]),axis=(1,2))
    longest=max_run(adjacent<.18)
    black=frames[ACTIVE_END:]
    black_pixel_ratio=float(np.mean(black<4))
    with (ROOT/"generated/revised-shot-plan.csv").open(newline="",encoding="utf-8-sig") as fh: rows=list(csv.DictReader(fh))
    shot_results=[]
    for row in rows:
        a=round(float(row["start_seconds"])*FPS); b=min(EXPECTED,round(float(row["end_seconds"])*FPS)); channels=[x for x in row["motion_channels"].split(";") if x]
        intentional=row["recovery_arc"]=="END"
        local=d12[a:max(a+1,min(len(d12),b-12))] if a<len(d12) else np.array([0.])
        energy=float(np.mean(local))
        shot_results.append({"id":row["id"],"start_frame":a,"end_frame":b,"section":row["section"],"location":row["location"],"recovery_arc":row["recovery_arc"],"motion_channels":channels,"declared_channels":len(channels),"mean_delta_12":round(energy,4),"intentional_black_or_audio_only":intentional,"motion_pass":intentional or energy>=.45})
    checks={
        "master_exists":VIDEO.exists(),
        "resolution_1920x1080":(video["width"],video["height"])==(1920,1080),
        "fps_30":video["r_frame_rate"]=="30/1",
        "frame_count_7525":len(frames)==int(video["nb_read_frames"])==EXPECTED,
        "video_duration":abs(float(video["duration"])-DURATION)<.001,
        "audio_duration_match":abs(float(audio["duration"])-float(video["duration"]))<1/FPS,
        "no_frame_gaps":len(frames)==EXPECTED,
        "active_timeline_no_static_run_over_12":longest<=12,
        "active_timeline_delta12":float(np.mean(d12))>=.45,
        "active_timeline_delta24":float(np.mean(d24))>=.65,
        "intentional_outro_black":black_pixel_ratio>.965,
        "all_non_end_shots_have_three_declared_channels":all(s["declared_channels"]>=3 for s in shot_results if not s["intentional_black_or_audio_only"]),
        "all_shots_motion_pass":all(s["motion_pass"] for s in shot_results),
        "shot_plan_complete":len(shot_results)==51 and shot_results[0]["start_frame"]==0 and shot_results[-1]["end_frame"]==EXPECTED,
    }
    report={"status":"PASS" if all(checks.values()) else "FAIL","file":"renders/master_1080p.mp4","checks":checks,"metrics":{"video_frames":len(frames),"video_duration":float(video["duration"]),"audio_duration":float(audio["duration"]),"longest_active_static_run":longest,"active_adjacent_mean":round(float(np.mean(adjacent)),4),"active_delta12_mean":round(float(np.mean(d12)),4),"active_delta24_mean":round(float(np.mean(d24)),4),"outro_black_pixel_ratio":round(black_pixel_ratio,6),"master_bytes":VIDEO.stat().st_size},"shots":shot_results,"method":"Decoded every master frame at 160x90 grayscale. Static and motion checks exclude the authored black/audio-only tail beginning at 241.74s; that tail is separately validated for black coverage."}
    (ROOT/"generated/full-motion-qa.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (ROOT/"generated/shot-report.json").write_text(json.dumps({"composition":{"frames":EXPECTED,"fps":FPS,"duration_seconds":DURATION,"audio":"audio/come_get_your_vitals.mp3"},"shots":shot_results},indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"checks":checks,"metrics":report["metrics"]},indent=2))
    if report["status"]!="PASS": raise SystemExit(1)


if __name__=="__main__": main()
