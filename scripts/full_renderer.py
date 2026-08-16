from __future__ import annotations

import csv
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import render_motion_proof as core


ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = core.W, core.H, 30
PRODUCTION = json.loads((ROOT / "production-config.json").read_text(encoding="utf-8"))
VISUAL = json.loads((ROOT / "visual-config.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "character-registry.json").read_text(encoding="utf-8"))
POSES = json.loads((ROOT / "generated" / "pose-manifest.json").read_text(encoding="utf-8"))
CLIENT_SPRITES = json.loads((ROOT / "generated" / "client-sprite-manifest.json").read_text(encoding="utf-8"))


with (ROOT / "generated" / "revised-shot-plan.csv").open(newline="", encoding="utf-8-sig") as f:
    SHOTS = list(csv.DictReader(f))

ENV = {
    "outside": Image.open(ROOT / "assets" / "env_outside_fishbowl.png").convert("RGB"),
    "detox": Image.open(ROOT / "assets" / "env_detox_window.png").convert("RGB"),
    "detox_station": Image.open(ROOT / "assets" / "env_detox_station.png").convert("RGB"),
    "residential": Image.open(ROOT / "assets" / "env_residential_window.png").convert("RGB"),
    "residential_station": Image.open(ROOT / "assets" / "env_residential_station.png").convert("RGB"),
}

CLIENTS = {c["id"]: c for c in REGISTRY["clients"]}
CLIENT_STYLE = {
    "CLIENT_01": ((151,139,112),(116,73,43),"disc"),
    "CLIENT_02": ((54,52,48),(166,73,34),"stocky"),
    "CLIENT_03": ((218,211,185),(35,37,36),"triangle"),
    "CLIENT_04": ((156,145,55),(55,59,28),"box"),
    "CLIENT_05": ((164,170,168),(172,103,61),"long"),
    "CLIENT_06": ((107,65,143),(166,51,116),"dart"),
    "CLIENT_07": ((45,46,45),(158,54,48),"stocky"),
    "CLIENT_08": ((228,204,155),(190,118,36),"flow"),
    "CLIENT_09": ((42,52,61),(221,194,144),"cat"),
    "CLIENT_10": ((171,128,54),(37,124,124),"seahorse"),
}

NURSE_ALIASES = {
    "orca":"NURSE_ORCA", "betta":"NURSE_BETTA", "puffer":"NURSE_PUFFER",
    "rainbow":"NURSE_RAINBOW", "tang":"NURSE_TANG", "clown":"NURSE_CLOWN",
}


def fnt(size: int, bold=False):
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{'seguisb' if bold else 'segoeui'}.ttf", size)
    except OSError:
        return ImageFont.load_default()


def shot_at(t: float) -> tuple[int, dict]:
    for i, s in enumerate(SHOTS):
        if float(s["start_seconds"]) <= t < float(s["end_seconds"]):
            return i, s
    return len(SHOTS)-1, SHOTS[-1]


def local_time(shot: dict, t: float) -> tuple[float, float]:
    start, end = float(shot["start_seconds"]), float(shot["end_seconds"])
    return t-start, core.clamp((t-start)/max(.001,end-start))


def recovery_mix(t: float) -> float:
    # Begins before midpoint, becomes residential-dominant only after beat return.
    if t < 110: return 0.0
    if t < 175.5: return core.smooth(110,175.5,t)
    return min(1.0,.82+core.smooth(175.5,224.78,t)*.18)


def background_for(t: float, shot: dict) -> Image.Image:
    loc = shot["location"].lower()
    _, u = local_time(shot,t)
    zoom = 1.02 + .025*math.sin(t*.071) + .014*u
    focus_x = .5 + .045*math.sin(t*.053)
    if t < 2.6:
        return core.cover(ENV["outside"],zoom=1+.10*core.smooth(0,2.6,t),focus=(.64,.45))
    if 2.6 <= t < 8.76:
        push = core.smooth(2.6,8.76,t)
        return core.cover(ENV["outside"],zoom=1.12+1.25*push,focus=(.80,.44))
    if 142.06 <= t < 175.5:
        bg = core.cover(ENV["residential"],zoom=1.01,focus=(.5,.48))
        return ImageEnhance.Color(bg).enhance(.58)
    if 204.46 <= t <= 229.34:
        traverse = core.clamp((t-204.46)/(229.34-204.46))
        if traverse < .33:
            return core.cover(ENV["detox"],zoom=1.06,focus=(.72-.28*traverse/.33,.48))
        if traverse < .67:
            return core.cover(ENV["outside"],zoom=1.30,focus=(.74-(traverse-.33)/.34*.48,.45))
        return core.cover(ENV["residential"],zoom=1.04,focus=(.62-(traverse-.67)/.33*.18,.48))
    if "residential station" in loc:
        key="residential_station"
    elif "residential" in loc or "center-left" in loc or "center-to-left" in loc:
        key="residential"
    elif "outside" in loc or "whole set" in loc:
        key="outside"
    elif "center" in loc and recovery_mix(t)>.45:
        key="residential"
    elif "station" in loc:
        key="detox_station"
    else:
        key="detox"
    return core.cover(ENV[key],zoom=zoom,focus=(focus_x,.48))


def grade(im: Image.Image, t: float, shot: dict) -> Image.Image:
    if 142.06 <= t < 175.5:
        state="bridge"
    else:
        mix=recovery_mix(t)
        state="detox" if mix<.30 else "center" if mix<.72 else "residential"
    lc=VISUAL["lighting"][state]
    wc=VISUAL["water"][state]
    im=ImageEnhance.Color(im).enhance(.55+wc["clarity"]*.62)
    im=ImageEnhance.Contrast(im).enhance(lc["contrast"])
    im=ImageEnhance.Brightness(im).enhance(.70+wc["clarity"]*.30)
    tint=Image.new("RGB",im.size,wc["hue"])
    im=Image.blend(im,tint,.11 if state!="bridge" else .16)
    return im


@lru_cache(maxsize=128)
def pose_image(cid: str, index: int) -> Image.Image:
    entries=POSES["characters"][cid]["poses"]
    item=entries[index%len(entries)]
    return Image.open(ROOT/item["file"]).convert("RGBA")


@lru_cache(maxsize=64)
def client_sprite(cid: str, state_index: int) -> Image.Image:
    item=CLIENT_SPRITES["clients"][cid][state_index]
    return Image.open(ROOT/item["file"]).convert("RGBA")


def client_sprite_mix(t: float) -> tuple[int,int,float]:
    if t<110: return 0,0,0.0
    if t<175.5: return 0,1,core.smooth(110,175.5,t)
    return 1,2,core.smooth(175.5,229.34,t)


def alpha_scaled(im: Image.Image, opacity: float) -> Image.Image:
    if opacity >= .999: return im
    out=im.copy(); out.putalpha(out.getchannel("A").point(lambda a: round(a*opacity))); return out


def draw_nurse(layer: Image.Image, cid: str, x: float, y: float, height: int, t: float, shot_index: int, phase: float):
    entries=POSES["characters"][cid]["poses"]
    cycle=1.45 if cid in {"NURSE_BETTA","NURSE_TANG","NURSE_CLOWN"} else 2.2
    base=shot_index+int((t+phase)/cycle)
    transition=((t+phase)%cycle)/cycle
    a=pose_image(cid,base)
    b=pose_image(cid,base+1)
    art_a=core.swim_warp(a,height,t+phase,5.5)
    art_b=core.swim_warp(b,height,t+phase+.23,5.5)
    blend=core.smooth(.72,.96,transition)
    if cid=="NURSE_PUFFER" and any(abs(t-v)<1.5 for v in (56.4,112.06,229.34,237.66)):
        blend=max(blend,core.smooth(0,1.2,1.5-min(abs(t-v) for v in (56.4,112.06,229.34,237.66))))
    art_a=alpha_scaled(art_a,1-blend)
    art_b=alpha_scaled(art_b,blend)
    bob=math.sin(t*1.6+phase)*7
    layer.alpha_composite(art_a,(round(x-art_a.width/2),round(y-art_a.height/2+bob)))
    layer.alpha_composite(art_b,(round(x-art_b.width/2),round(y-art_b.height/2+bob)))
    # Independent expressive emphasis ring and gesture fin provide motion even
    # between source-pose transitions.
    d=ImageDraw.Draw(layer)
    gx=x+height*.23; gy=y+math.sin(t*3+phase)*height*.07
    d.ellipse((gx-5,gy-5,gx+5,gy+5),fill=(225,242,247,210))


def client_state(t: float) -> dict:
    if t < 110: return VISUAL["client_states"]["detox"]
    if t < 175.5:
        a,b=VISUAL["client_states"]["detox"],VISUAL["client_states"]["stabilizing"]
        u=core.smooth(110,175.5,t)
    else:
        a,b=VISUAL["client_states"]["stabilizing"],VISUAL["client_states"]["residential"]
        u=core.smooth(175.5,229.34,t)
    return {k:a[k]+(b[k]-a[k])*u for k in a}


def draw_generic_client(layer: Image.Image, cid: str, x: float, y: float, scale: float, t: float, phase: float, direction=1):
    primary,accent,shape=CLIENT_STYLE[cid]
    st=client_state(t); sat=st["saturation"]
    def muted(c):
        mean=sum(c)/3
        return tuple(round(mean+(v-mean)*sat) for v in c)+(245,)
    pc,ac=muted(primary),muted(accent)
    d=ImageDraw.Draw(layer)
    swim=st["swim_energy"]
    bob=math.sin(t*(.7+swim)+phase)*8*scale
    tail=math.sin(t*(2.4+swim*2)+phase)*13*scale
    y+=bob-(st["posture"]-.22)*22*scale
    flip=direction
    if shape=="seahorse":
        d.ellipse((x-18*scale,y-46*scale,x+20*scale,y+10*scale),fill=pc,outline=ac,width=max(1,round(2*scale)))
        pts=[(x,y+5*scale),(x+6*scale,y+30*scale),(x-2*scale,y+52*scale),(x-18*scale,y+49*scale),(x-20*scale,y+34*scale)]
        d.line(pts,fill=pc,width=max(5,round(15*scale)),joint="curve")
        d.arc((x-23*scale,y+31*scale,x+6*scale,y+61*scale),40,330,fill=ac,width=max(2,round(4*scale)))
        eye_x=x+10*scale
    else:
        dims={"disc":(38,48),"stocky":(55,34),"triangle":(40,52),"box":(45,31),"long":(68,25),"dart":(57,23),"flow":(54,31),"cat":(60,27)}
        bw,bh=dims[shape]; bw*=scale; bh*=scale
        d.ellipse((x-bw,y-bh,x+bw,y+bh),fill=pc,outline=ac,width=max(1,round(2*scale)))
        tx=x-flip*bw
        d.polygon([(tx,y),(tx-flip*34*scale,y-25*scale-tail),(tx-flip*31*scale,y+25*scale-tail)],fill=ac)
        if shape in {"triangle","dart"}:
            d.polygon([(x-8*scale,y-bh),(x+8*scale,y-bh-38*scale-tail*.2),(x+21*scale,y-bh)],fill=ac)
        if shape=="flow":
            d.polygon([(tx,y),(tx-flip*52*scale,y-34*scale-tail),(tx-flip*43*scale,y+36*scale-tail)],fill=(238,214,170,190))
        if shape=="cat":
            for k in (-1,1): d.line((x+flip*bw*.7,y+k*5*scale,x+flip*(bw+28*scale),y+k*12*scale+tail*.1),fill=ac,width=max(1,round(scale)))
        # Immutable identifiers rendered as accent marks.
        if cid=="CLIENT_01": d.ellipse((x-flip*24*scale,y-27*scale,x-flip*8*scale,y-11*scale),fill=(18,22,22,255))
        elif cid=="CLIENT_04": d.polygon([(x,y-8*scale),(x+8*scale,y),(x,y+8*scale),(x-8*scale,y)],fill=(224,220,185,230))
        elif cid=="CLIENT_08": d.ellipse((x-3*scale,y-22*scale,x+12*scale,y-8*scale),fill=(178,52,45,240))
        eye_x=x+flip*bw*.63
    eye_y=y-9*scale
    brightness=st["eye_brightness"]
    d.ellipse((eye_x-7*scale,eye_y-7*scale,eye_x+7*scale,eye_y+7*scale),fill=(235,242,238,255),outline=(12,20,24,255),width=max(1,round(scale)))
    d.ellipse((eye_x-2.8*scale,eye_y-3.5*scale,eye_x+2.8*scale,eye_y+3.5*scale),fill=(round(120+120*brightness),round(75+90*brightness),35,255))
    d.ellipse((eye_x-1.2*scale,eye_y-2*scale,eye_x+1.2*scale,eye_y+2*scale),fill=(3,8,12,255))
    if t<135:
        blanket_y=y+31*scale
        d.polygon([(x-55*scale,blanket_y),(x-27*scale,blanket_y-13*scale),(x+32*scale,blanket_y-7*scale),(x+50*scale,blanket_y+16*scale),(x-52*scale,blanket_y+17*scale)],fill=(42,48,60,round(215*(1-core.smooth(115,140,t)))))
    # The approved concept art supplies the premium visible surface while the
    # deterministic primitive rig underneath continues to drive tail, posture,
    # whisker and secondary-fin motion.
    ia,ib,mix=client_sprite_mix(t)
    target_h=round((105 if shape not in {"long","dart"} else 82)*scale)
    native_facing=-1 if int(cid[-2:])<=5 else 1
    def prepared(index,opacity,offset):
        art=client_sprite(cid,index)
        if native_facing!=direction: art=art.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        art=core.swim_warp(art,target_h,t+phase+offset,3.2*scale)
        return alpha_scaled(art,opacity)
    art_a=prepared(ia,1-mix if ia!=ib else 1.0,0)
    layer.alpha_composite(art_a,(round(x-art_a.width/2),round(y-art_a.height/2)))
    if ia!=ib and mix>0:
        art_b=prepared(ib,mix,.17)
        layer.alpha_composite(art_b,(round(x-art_b.width/2),round(y-art_b.height/2)))


def parse_cast(value: str, shot_index: int) -> tuple[list[str], list[str]]:
    low=value.lower()
    nurses=[]; clients=[]
    if "ensemble" in low or "all nurses" in low:
        nurses=list(NURSE_ALIASES.values())
    else:
        for alias,cid in NURSE_ALIASES.items():
            if alias in low: nurses.append(cid)
    for cid in CLIENTS:
        if cid.lower() in low: clients.append(cid)
    if "client" in low and not clients: clients=[f"CLIENT_{(shot_index%10)+1:02d}"]
    if "ensemble" in low and not clients: clients=["CLIENT_01","CLIENT_03","CLIENT_06","CLIENT_08"]
    if not nurses and not clients and "none" not in low: nurses=["NURSE_BETTA"]
    return nurses[:6],clients[:6]


def key_text(t: float) -> str | None:
    cues=[
        (56.4,59,"INTAKE'S HERE"),(82,85,"I CAN AND I WILL"),(104.3,108.3,"ALIVE"),
        (112.06,116.14,"CHAOS CLOCKS IN"),(138.14,141.3,"I CAN AND I WILL"),
        (152.54,154.62,"IT CAN HAPPEN TO ANYBODY"),(168.94,170.78,"I'M STILL CLEAN"),
        (224.78,229.34,"RECOVERY CAN TOO"),(229.34,232.14,"CODE BLUE"),
        (233.1,234.3,"DON'T. BE. A. MELODY."),(237.66,240.94,"INTAKE'S HERE")]
    for a,b,label in cues:
        if a<=t<b: return label
    return None


def frame_at(t: float) -> Image.Image:
    shot_index,shot=shot_at(t)
    local,u=local_time(shot,t)
    bg=grade(background_for(t,shot),t,shot)
    if 2.6<t<8.76:
        amount=22*(1-abs(u*2-1))
        bg=core.refract(bg,t,amount)
    base=core.draw_caustics(bg,t,.3+.65*recovery_mix(t))
    layer=Image.new("RGBA",(W,H))
    # Five-plane parallax cues: far fish, plants, cast, props, glass.
    d=ImageDraw.Draw(layer)
    for k in range(7):
        fx=(k*173+t*(9+2*k))%(W+100)-50
        fy=90+(k%4)*70+20*math.sin(t*.3+k)
        d.ellipse((fx-14,fy-7,fx+14,fy+7),fill=(70,145,154,38+round(40*recovery_mix(t))))
        d.polygon([(fx-14,fy),(fx-26,fy-8),(fx-26,fy+8)],fill=(70,145,154,38+round(40*recovery_mix(t))))
    core.draw_plant(layer,45,540,t,.3,(30,91,74,210))
    core.draw_plant(layer,895,545,t,1.4,(41,116,83,220))
    nurses,clients=parse_cast(shot["characters"],shot_index)
    # Clients occupy the lower/outer water and keep stable IDs.
    client_positions=[(185,395),(365,430),(535,390),(710,420),(830,365),(470,485)]
    for i,cid in enumerate(clients):
        x,y=client_positions[i%len(client_positions)]
        direction=1 if i%2==0 else -1
        x += math.sin(t*.2+i)*28
        draw_generic_client(layer,cid,x,y,.82 if i>2 else .95,t,i*.77,direction)
    # Nurses remain the constant, centered inside the station.
    nurse_positions=[(560,270),(705,280),(420,285),(790,250),(320,270),(625,380)]
    for i,cid in enumerate(nurses):
        x,y=nurse_positions[i%len(nurse_positions)]
        height=235 if len(nurses)<=3 else 175
        draw_nurse(layer,cid,x,y,height,t,shot_index,i*.41)
    # Recurring pulse ox and station props.
    if 5<t<58 or 40<t<51:
        px=500+330*((t*.09)%1); py=205+27*math.sin(t*1.8)
        d.rounded_rectangle((px-13,py-7,px+13,py+7),4,fill=(19,43,52,235),outline=(94,219,234,235),width=2)
        d.ellipse((px-4,py-3,px+3,py+3),fill=(242,77,82,245))
    if 51<t<59 or 112<t<116.2:
        for i in range(4):
            px=600+i*42+math.sin(t*(1.4+i*.17))*17; py=430-i*10+math.sin(t*2+i)*8
            d.rounded_rectangle((px-18,py-10,px+18,py+10),3,fill=(231,237,225,170))
    # Animated monitor waveform is code-native and never uses PHI.
    pts=[]
    for x in range(620,900,4):
        beat=((x-620)/45+t*2.53)%1
        yy=87-(28*(1-beat/.08) if beat<.08 else -10*(1-(beat-.08)/.08) if beat<.16 else 0)
        pts.append((x,yy))
    d.line(pts,fill=(79,239,198,175),width=2)
    core.draw_water(layer,t,murk=1-recovery_mix(t)*.55)
    # Foreground glass/reflection depth plane.
    for gx,phase in ((72,.1),(886,1.4)):
        xx=gx+10*math.sin(t*.42+phase)
        d.line((xx,0,xx+22*math.sin(t*.19+phase),H),fill=(205,242,248,34),width=3)
    out=Image.alpha_composite(base,layer)
    label=key_text(t)
    if label:
        td=ImageDraw.Draw(out)
        size=42 if len(label)<17 else 30
        ff=fnt(size,True); box=td.textbbox((0,0),label,font=ff,stroke_width=1)
        tw=box[2]-box[0]
        alpha=core.smooth(0,.18,local)*(1-core.smooth(max(.2,float(shot["duration"])-.3),float(shot["duration"]),local))
        td.rounded_rectangle((W/2-tw/2-22,36,W/2+tw/2+22,92),12,fill=(4,16,26,round(150*alpha)),outline=(121,230,234,round(170*alpha)),width=2)
        td.text((W/2-tw/2,43),label,font=ff,fill=(245,252,247,round(245*alpha)),stroke_width=1,stroke_fill=(4,18,24,round(220*alpha)))
    # Bridge gets additional negative-space vignette.
    if 142.06<=t<175.5:
        vign=Image.new("L",(W,H)); vd=ImageDraw.Draw(vign); vd.ellipse((60,15,W-60,H-15),fill=0); vign=vign.filter(ImageFilter.GaussianBlur(70))
        shade=Image.new("RGBA",(W,H),(2,8,13,0)); shade.putalpha(vign.point(lambda v: round(v*.62))); out=Image.alpha_composite(out,shade)
    # Authored black tail after final button.
    if t>=241.74:
        black=Image.new("RGB",(W,H),"black")
        if 247.74<=t<248.54:
            bd=ImageDraw.Draw(black); r=(t-247.74)*24+2; bd.ellipse((W/2-r,H*.72-r,W/2+r,H*.72+r),outline=(112,188,196,170),width=2)
        return black
    return out.convert("RGB")


def render_visual_contact_sheet(path: Path) -> None:
    times=[0.5,5.2,15,58,83,114,146,154,169.5,179,207,218,226.5,230,233.5,238.5]
    thumbs=[frame_at(t).resize((480,270),Image.Resampling.LANCZOS) for t in times]
    sheet=Image.new("RGB",(1920,1080),"#06131c")
    for i,(thumb,t) in enumerate(zip(thumbs,times)):
        x=(i%4)*480; y=(i//4)*270; sheet.paste(thumb,(x,y));
        dd=ImageDraw.Draw(sheet); dd.rectangle((x,y,x+115,y+24),fill=(3,12,20,190)); dd.text((x+6,y+3),f"{t:06.2f}s",font=fnt(14,True),fill="white")
    path.parent.mkdir(parents=True,exist_ok=True); sheet.save(path,quality=94)


if __name__=="__main__":
    render_visual_contact_sheet(ROOT/"generated"/"loop2-visual-contact-sheet.jpg")
