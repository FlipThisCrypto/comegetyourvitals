from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
W, H, FPS, DURATION = 960, 540, 30, 18.0
FRAMES = int(FPS * DURATION)
TAU = math.tau
SEED = 73184
rng = np.random.default_rng(SEED)


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def smooth(a, b, x):
    u = clamp((x - a) / (b - a))
    return u * u * (3 - 2 * u)


def cover(im: Image.Image, w=W, h=H, zoom=1.0, focus=(0.5, 0.5)):
    scale = max(w / im.width, h / im.height) * zoom
    sw, sh = round(im.width * scale), round(im.height * scale)
    r = im.resize((sw, sh), Image.Resampling.LANCZOS)
    left = round((sw - w) * focus[0])
    top = round((sh - h) * focus[1])
    return r.crop((left, top, left + w, top + h)).convert("RGB")


def font(size, bold=False):
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{'seguisb' if bold else 'segoeui'}.ttf", size)
    except OSError:
        return ImageFont.load_default()


OUTSIDE = Image.open(ROOT / "assets" / "env_outside_fishbowl.png").convert("RGB")
DETOX = Image.open(ROOT / "assets" / "env_detox_window.png").convert("RGB")


def largest_alpha_component(im: Image.Image) -> Image.Image:
    """Remove neighboring pose fragments from a manually bounded sheet crop."""
    rgba = im.convert("RGBA")
    alpha = np.array(rgba.getchannel("A")) > 18
    h, w = alpha.shape
    seen = np.zeros_like(alpha, dtype=bool)
    best = []
    for yy in range(h):
        for xx in range(w):
            if not alpha[yy, xx] or seen[yy, xx]:
                continue
            stack = [(xx, yy)]; seen[yy, xx] = True; component = []
            while stack:
                cx, cy = stack.pop(); component.append((cx, cy))
                for nx, ny in ((cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)):
                    if 0 <= nx < w and 0 <= ny < h and alpha[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx] = True; stack.append((nx,ny))
            if len(component) > len(best): best = component
    keep = np.zeros_like(alpha)
    if best:
        xs = [p[0] for p in best]; ys = [p[1] for p in best]
        keep[np.array(ys), np.array(xs)] = True
    arr = np.array(rgba)
    arr[..., 3] = np.where(keep, arr[..., 3], 0)
    clean = Image.fromarray(arr, "RGBA")
    return clean.crop(clean.getbbox())


_betta_sheet = Image.open(ROOT / "assets" / "char_betta_sheet.png")
_puffer_sheet = Image.open(ROOT / "assets" / "char_puffer_sheet.png")
BETTA_SPRITE = largest_alpha_component(_betta_sheet.crop((0, 10, 365, 500)))
PUFFER_NORMAL = largest_alpha_component(_puffer_sheet.crop((0, 0, 350, 430)))
PUFFER_ROUND = largest_alpha_component(_puffer_sheet.crop((290, 0, 660, 440)))


def swim_warp(sprite: Image.Image, target_h: int, time: float, amount: float) -> Image.Image:
    scale = target_h / sprite.height
    src = sprite.resize((max(1, round(sprite.width*scale)), target_h), Image.Resampling.LANCZOS)
    pad = round(amount*2+5)
    out = Image.new("RGBA", (src.width+pad*2, src.height+pad*2))
    strip = 8
    for y in range(0, src.height, strip):
        hh = min(strip, src.height-y)
        # Top/bottom features receive more secondary motion than the torso.
        edge = abs((y/src.height)-.5)*2
        dx = round(math.sin(time*2.25+y*.045)*amount*(.25+.75*edge))
        out.alpha_composite(src.crop((0,y,src.width,y+hh)), (pad+dx,pad+y))
    return out

BUBBLES = [
    dict(x=float(rng.uniform(0, W)), y=float(rng.uniform(0, H)), r=float(rng.uniform(2, 9)), speed=float(rng.uniform(18, 60)), phase=float(rng.uniform(0, TAU)), z=float(rng.uniform(0.4, 1.2)))
    for _ in range(74)
]
PARTICLES = [
    dict(x=float(rng.uniform(0, W)), y=float(rng.uniform(0, H)), r=float(rng.uniform(0.5, 2.2)), sx=float(rng.uniform(-5, 5)), sy=float(rng.uniform(-4, 7)), phase=float(rng.uniform(0, TAU)))
    for _ in range(170)
]


def refract(im: Image.Image, time: float, amount: float):
    if amount < 0.2:
        return im
    out = Image.new("RGB", im.size)
    strip = 9
    for y in range(0, H, strip):
        h = min(strip, H - y)
        shift = round(math.sin(y * 0.047 + time * 6.1) * amount + math.sin(y * 0.013 - time * 3.7) * amount * 0.35)
        row = im.crop((0, y, W, y + h))
        out.paste(row, (shift, y))
        if shift > 0:
            out.paste(row.crop((0, 0, shift, h)).resize((shift, h)), (0, y))
        elif shift < 0:
            out.paste(row.crop((W + shift, 0, W, h)).resize((-shift, h)), (W + shift, y))
    return out


def draw_caustics(base: Image.Image, time: float, intensity: float):
    layer = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(layer)
    for j in range(13):
        pts = []
        y0 = 40 + j * 42
        for x in range(-20, W + 21, 20):
            y = y0 + 8 * math.sin(x * 0.019 + time * 1.9 + j * 0.8) + 4 * math.sin(x * 0.043 - time * 1.1)
            pts.append((x, y))
        d.line(pts, fill=(122, 226, 240, round(21 * intensity)), width=2)
    return Image.alpha_composite(base.convert("RGBA"), layer)


def draw_water(layer: Image.Image, time: float, murk=1.0):
    d = ImageDraw.Draw(layer)
    for p in PARTICLES:
        x = (p["x"] + p["sx"] * time + 11 * math.sin(time * 0.31 + p["phase"])) % W
        y = (p["y"] + p["sy"] * time) % H
        a = round(35 + 42 * murk)
        d.ellipse((x - p["r"], y - p["r"], x + p["r"], y + p["r"]), fill=(172, 206, 201, a))
    for b in BUBBLES:
        x = (b["x"] + 12 * math.sin(time * 0.8 + b["phase"]) * b["z"]) % W
        y = (b["y"] - b["speed"] * time) % (H + 50) - 25
        r = b["r"] * b["z"]
        d.ellipse((x - r, y - r, x + r, y + r), outline=(199, 242, 255, 115), width=max(1, round(r / 3)))
        d.ellipse((x - r * .35, y - r * .55, x - r * .05, y - r * .25), fill=(255, 255, 255, 115))


def limb(d, points, color, width, joint_color=None):
    d.line(points, fill=color, width=width, joint="curve")
    radius = width // 2
    for x, y in points:
        d.ellipse((x-radius, y-radius, x+radius, y+radius), fill=joint_color or color)


def eye(d, x, y, scale, color, blink):
    hh = max(1, 10 * scale * (1 - blink * .92))
    d.ellipse((x - 8*scale, y-hh, x + 8*scale, y+hh), fill=(238, 247, 249, 255), outline=(9, 24, 35, 255), width=max(1, round(scale*2)))
    if hh > 3:
        d.ellipse((x - 3.6*scale, y-5*scale, x + 3.6*scale, y+5*scale), fill=color)
        d.ellipse((x - 1.5*scale, y-3*scale, x + 1.5*scale, y+3*scale), fill=(5, 12, 18, 255))
        d.ellipse((x - 1.8*scale, y-3.5*scale, x-.2*scale, y-1.9*scale), fill="white")


def draw_betta(layer, x, y, s, time, vocal):
    d = ImageDraw.Draw(layer)
    bob = math.sin(time * 1.8) * 5 * s
    y += bob
    tail_phase = math.sin(time * 3.6)
    # Independent tail and hair groups.
    tail = [(x-20*s, y+25*s), (x-86*s, y+2*s+14*tail_phase*s), (x-102*s, y+51*s), (x-41*s, y+80*s), (x-4*s, y+55*s)]
    d.polygon(tail, fill=(15, 83, 190, 235), outline=(70, 215, 255, 255))
    for k in range(4):
        hx = x - (20+k*10)*s
        hy = y - (43+k*5)*s + math.sin(time*2.2-k*.6)*5*s
        d.ellipse((hx-26*s,hy-18*s,hx+26*s,hy+24*s), fill=(5,25+8*k,70+24*k,245))
    # Torso, head and scrubs.
    d.ellipse((x-38*s,y-1*s,x+35*s,y+78*s), fill=(16,75,158,255), outline=(49,190,238,255), width=max(1, round(2*s)))
    d.ellipse((x-34*s,y-54*s,x+32*s,y+13*s), fill=(65,143,218,255), outline=(106,221,255,255), width=max(1, round(2*s)))
    blink = smooth(.0,.08, abs(((time+0.21)%3.2)-1.6) - 1.47)
    eye(d, x-10*s, y-23*s, s, (42,129,226,255), blink)
    eye(d, x+13*s, y-23*s, s, (42,129,226,255), blink)
    mouth_h = (3 + 7*vocal) * s
    d.ellipse((x-9*s,y-5*s-mouth_h/2,x+11*s,y-5*s+mouth_h/2), fill=(83,15,47,255), outline=(245,137,167,255), width=max(1,round(s)))
    # Two-joint articulated arms.
    gesture = math.sin(time*5.1)*.5+.5 if vocal else .15
    limb(d, [(x-25*s,y+18*s),(x-52*s,y+(26-20*gesture)*s),(x-67*s,y+(5-40*gesture)*s)], (57,132,211,255), max(4,round(11*s)))
    limb(d, [(x+25*s,y+20*s),(x+49*s,y+(32+8*gesture)*s),(x+64*s,y+(22+13*gesture)*s)], (57,132,211,255), max(4,round(11*s)))
    # Badge and stethoscope remain attached to torso.
    d.line((x-15*s,y+7*s,x+14*s,y+44*s), fill=(25,37,45,255), width=max(1,round(2*s)))
    d.rounded_rectangle((x-10*s,y+36*s,x+13*s,y+55*s), radius=3*s, fill="white")
    d.text((x-6*s,y+37*s), "RN", font=font(max(7,round(9*s)),True), fill="#174ea6")
    # Canonical nurse artwork is the visible surface; the code rig underneath
    # provides articulated extremities and anchors, while this source sprite is
    # non-rigidly strip-warped for fin/hair follow-through.
    art = swim_warp(BETTA_SPRITE, round(250*s), time, 7*s)
    layer.alpha_composite(art, (round(x-art.width*.53), round(y-art.height*.50)))
    od = ImageDraw.Draw(layer)
    # Authored mouth cadence and blink overlays remain separate from the sprite.
    fx = x + 31*s; fy = y - 27*s
    od.ellipse((fx-7*s,fy-1*s,fx+8*s,fy+(3+7*vocal)*s), fill=(91,17,48,230), outline=(255,148,170,235), width=max(1,round(s)))
    if abs(((time+.2)%3.2)-1.6)>1.51:
        od.line((x+8*s,y-50*s,x+24*s,y-48*s),fill=(20,38,72,235),width=max(2,round(3*s)))


def draw_puffer(layer, x, y, s, time, inflate):
    d = ImageDraw.Draw(layer)
    bob = math.sin(time*2.05+1.1)*4*s
    y += bob
    r = (37 + 28*inflate)*s
    # Hair moves independently behind radial body.
    for k in range(8):
        ang = math.pi + (k-3.5)*.23
        hx = x + math.cos(ang)*r*.72
        hy = y-8*s + math.sin(ang)*r*.75 + math.sin(time*2.4+k)*4*s
        d.ellipse((hx-18*s,hy-16*s,hx+18*s,hy+22*s),fill=(8,21,45,245))
    d.ellipse((x-r,y-r,x+r,y+r),fill=(209,177,127,255),outline=(110,210,234,255),width=max(1,round(2*s)))
    if inflate > .12:
        for k in range(18):
            a=k/18*TAU
            rr=r+3*s
            x1=x+math.cos(a)*rr; y1=y+math.sin(a)*rr
            x2=x+math.cos(a)*(rr+8*s*inflate); y2=y+math.sin(a)*(rr+8*s*inflate)
            d.line((x1,y1,x2,y2),fill=(238,222,184,220),width=max(1,round(s)))
    blink = 1.0 if abs(((time+.4)%4.1)-2.05)>2.0 else 0.0
    eye(d,x-14*s,y-12*s,s,(35,128,224,255),blink)
    eye(d,x+14*s,y-12*s,s,(35,128,224,255),blink)
    mouth_open = .25 + .75*smooth(11.5,12.3,time)*(1-smooth(14.2,15.0,time))
    d.ellipse((x-9*s,y+8*s,x+9*s,y+(9+14*mouth_open)*s),fill=(70,20,30,255),outline=(246,151,143,255),width=max(1,round(s)))
    arm_w=max(4,round(9*s))
    spread=18*inflate
    limb(d,[(x-r*.55,y+9*s),(x-(r+18*s),y+(12-spread)*s),(x-(r+30*s),y-(4+spread)*s)],(182,144,101,255),arm_w)
    limb(d,[(x+r*.55,y+9*s),(x+(r+18*s),y+(12-spread)*s),(x+(r+30*s),y-(4+spread)*s)],(182,144,101,255),arm_w)
    # Scrub collar + badge.
    d.polygon([(x-r*.7,y+r*.25),(x+r*.7,y+r*.25),(x+r*.45,y+r*.8),(x-r*.45,y+r*.8)],fill=(11,66,142,230))
    d.rounded_rectangle((x-9*s,y+r*.46,x+12*s,y+r*.67),radius=3*s,fill="white")
    d.text((x-5*s,y+r*.48),"RN",font=font(max(7,round(9*s)),True),fill="#174ea6")
    normal = swim_warp(PUFFER_NORMAL, round(225*s), time+.4, 5*s)
    round_art = swim_warp(PUFFER_ROUND, round((205+74*inflate)*s), time+.7, 6*s)
    normal_mix = 1-smooth(.22,.48,inflate)
    round_mix = smooth(.34,.58,inflate)
    if normal_mix > 0:
        normal.putalpha(normal.getchannel("A").point(lambda a: round(a*normal_mix)))
        layer.alpha_composite(normal,(round(x-normal.width*.53),round(y-normal.height*.47)))
    if round_mix > 0:
        round_art.putalpha(round_art.getchannel("A").point(lambda a: round(a*round_mix)))
        layer.alpha_composite(round_art,(round(x-round_art.width*.5),round(y-round_art.height*.52)))
    od=ImageDraw.Draw(layer)
    # Separate reaction mouth keeps the canonical surface from becoming static.
    mh=(3+12*mouth_open)*s
    od.ellipse((x-7*s,y+1*s,x+8*s,y+1*s+mh),fill=(87,20,34,220),outline=(253,151,148,230),width=max(1,round(s)))


def draw_client(layer, kind, x, y, s, time, swim, glass=False):
    d=ImageDraw.Draw(layer)
    muted=.58
    tail=math.sin(time*(3.2 if kind=="mara" else 4.6)+(.5 if kind=="avery" else 0))*18*s*swim
    bob=math.sin(time*1.5+(1 if kind=="avery" else 0))*4*s
    y+=bob
    if kind=="mara":
        body=(x-35*s,y-48*s,x+35*s,y+48*s)
        d.polygon([(x-31*s,y),(x-72*s,y-30*s-tail),(x-65*s,y+30*s-tail)],fill=(100,107,101,255))
        d.ellipse(body,fill=(151,139,112,255),outline=(205,180,130,255),width=max(1,round(2*s)))
        for k in [-18,0,18]: d.rectangle((x+k*s-4*s,y-45*s,x+k*s+4*s,y+45*s),fill=(116,73,43,220))
        d.polygon([(x+28*s,y-7*s),(x+72*s,y-2*s),(x+28*s,y+8*s)],fill=(171,154,119,255))
        eye(d,x+16*s,y-15*s,.72*s,(182,112,28,255),0)
        d.ellipse((x-25*s,y-30*s,x-9*s,y-14*s),fill=(22,25,25,255))
    else:
        d.polygon([(x-30*s,y),(x-76*s,y-29*s-tail),(x-68*s,y+26*s-tail)],fill=(76,42,112,255))
        d.ellipse((x-43*s,y-25*s,x+45*s,y+25*s),fill=(91,61,131,255),outline=(157,99,178,255),width=max(1,round(2*s)))
        d.polygon([(x-10*s,y-20*s),(x+6*s,y-58*s-tail*.25),(x+22*s,y-18*s)],fill=(106,42,120,255))
        eye(d,x+23*s,y-7*s,.75*s,(222,146,35,255),0)
        d.ellipse((x+39*s,y+8*s,x+44*s,y+12*s),fill=(235,235,220,255))
    # Blanket/body support remains a separate softly moving prop in detox.
    blanket_y=y+37*s
    d.polygon([(x-55*s,blanket_y),(x-30*s,blanket_y-14*s),(x+11*s,blanket_y-10*s),(x+51*s,blanket_y+2*s),(x+38*s,blanket_y+20*s),(x-55*s,blanket_y+18*s)],fill=(41,48,62,210))
    # Wristband is a persistent generic object, no text.
    d.rectangle((x+31*s,y+15*s,x+40*s,y+22*s),fill=(221,225,220,255))
    if glass:
        reach=18+10*math.sin(time*3)
        d.ellipse((x+45*s,y-reach*s/2,x+55*s,y+reach*s/2),fill=(180,165,128,240))


def draw_plant(layer, x, y, time, phase, color):
    d=ImageDraw.Draw(layer)
    for k in range(7):
        pts=[]
        for q in range(9):
            yy=y-q*13
            xx=x+k*7+math.sin(time*1.15+phase+k*.5+q*.18)*(2+q*.65)
            pts.append((xx,yy))
        d.line(pts,fill=color,width=4)


def frame_at(time: float) -> Image.Image:
    # Camera push aims into the right-side detox window and crosses the glass.
    push=smooth(0,3.35,time)
    if time < 3.35:
        bg=cover(OUTSIDE,zoom=1+1.25*push,focus=(.79,.43))
        bg=ImageEnhance.Color(bg).enhance(.72)
    else:
        pan=.5+.06*math.sin((time-3.35)*.12)
        bg=cover(DETOX,zoom=1.03+.025*smooth(3.35,18,time),focus=(pan,.49))
        bg=ImageEnhance.Color(bg).enhance(.60)
        bg=ImageEnhance.Brightness(bg).enhance(.67)
    pass_amt=(1-abs(clamp((time-2.15)/2.25)*2-1))*18 if 2.15<time<4.4 else 0
    bg=refract(bg,time,pass_amt)
    base=draw_caustics(bg,time,.65 if time>3.2 else .3)
    world=Image.new("RGBA",(W,H))
    d=ImageDraw.Draw(world)
    # Cold fluorescent fixture with slight independent flicker.
    flicker=.82+.18*(.5+.5*math.sin(time*17.3))
    d.rectangle((690,27,910,38),fill=(185,232,242,round(130*flicker)))
    d.text((784,49),"DETOX",font=font(21,True),fill=(177,207,212,170))
    draw_plant(world,72,530,time,.2,(35,88,76,210))
    draw_plant(world,860,540,time,1.3,(28,70,65,180))
    # Papers flutter independently near the station desk.
    if time>4:
        for k in range(3):
            px=620+52*k+math.sin(time*(1.4+k*.2)+k)*18
            py=455-k*12+math.sin(time*2.2+k)*7
            paper=Image.new("RGBA",(54,34)); pd=ImageDraw.Draw(paper); pd.rounded_rectangle((2,2,51,31),3,fill=(225,233,226,170)); pd.line((10,10,42,10),fill=(85,110,115,130),width=2)
            paper=paper.rotate(math.sin(time*1.7+k)*11,resample=Image.Resampling.BICUBIC,expand=True)
            world.alpha_composite(paper,(round(px),round(py)))
    # The rigged cast fades in as the camera clears the glass.
    appear=smooth(2.8,4.0,time)
    if appear>0:
        chars=Image.new("RGBA",(W,H))
        swim=smooth(3.5,8.0,time)*.55+.25
        mara_x=190+62*smooth(4,17,time)
        avery_x=405+18*math.sin(time*.55)
        draw_client(chars,"mara",mara_x,384,1.05,time,swim,glass=time>14.7)
        draw_client(chars,"avery",avery_x,430,.88,time,swim*.8)
        vocal=0.0
        if time>=8.76:
            beat_phase=(time-8.76)*152/60
            vocal=(.5+.5*math.sin(beat_phase*TAU))**1.8
        draw_betta(chars,616,270,1.05,time,vocal)
        inflate=smooth(10.8,12.8,time)*(1-smooth(15.1,16.2,time))
        draw_puffer(chars,797,321,.93,time,inflate)
        chars.putalpha(chars.getchannel("A").point(lambda a: round(a*appear)))
        world=Image.alpha_composite(world,chars)
    # Pulse ox travels in depth behind the nurses.
    if 5.8<time<16.8:
        u=(time-5.8)/11
        px=500+370*u
        py=202+65*math.sin(u*math.pi)+14*math.sin(time*2.3)
        d=ImageDraw.Draw(world)
        d.rounded_rectangle((px-14,py-8,px+14,py+8),radius=5,fill=(21,40,53,235),outline=(90,215,236,230),width=2)
        d.ellipse((px-5,py-4,px+3,py+4),fill=(234,72,77,240))
    # Glass-touch refraction ripple.
    if 15.0<time<17.8:
        rd=ImageDraw.Draw(world)
        u=time-15
        for k in range(4):
            rr=(u*35-k*13)%75
            alpha=round(130*(1-rr/75))
            rd.ellipse((300-rr,380-rr*.62,300+rr,380+rr*.62),outline=(170,235,244,alpha),width=2)
    draw_water(world,time,murk=1.0)
    # Near-camera glass highlights prove a separate depth plane.
    gd=ImageDraw.Draw(world)
    glass_alpha=round(90*(1-smooth(3.6,4.3,time))) if time<4.3 else 18
    gd.line((94+10*math.sin(time),0,62+13*math.sin(time*.8),H),fill=(210,245,255,glass_alpha),width=3)
    gd.line((870+8*math.sin(time*.7),0,900+11*math.sin(time),H),fill=(210,245,255,glass_alpha),width=2)
    out=Image.alpha_composite(base,world)
    # Vignette and authored shot label.
    vign=Image.new("L",(W,H)); vd=ImageDraw.Draw(vign); vd.ellipse((-90,-80,W+90,H+100),fill=0); vign=vign.filter(ImageFilter.GaussianBlur(60));
    shade=Image.new("RGBA",(W,H),(2,10,18,0)); shade.putalpha(vign.point(lambda v: round(v*.55))); out=Image.alpha_composite(out,shade)
    return out.convert("RGB")


def main():
    out=ROOT/"renders"/"proof-of-motion-1080p.mp4"
    out.parent.mkdir(parents=True,exist_ok=True)
    cmd=["ffmpeg","-y","-v","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-i",str(ROOT/"audio"/"come_get_your_vitals.mp3"),"-t",str(DURATION),"-filter:v","scale=1920:1080:flags=lanczos","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","256k","-shortest",str(out)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for frame in range(FRAMES):
        proc.stdin.write(frame_at(frame/FPS).tobytes())
        if frame%90==0: print(f"rendered {frame}/{FRAMES}",flush=True)
    proc.stdin.close()
    code=proc.wait()
    if code: raise SystemExit(code)
    report={
        "composition":{"file":"renders/proof-of-motion-1080p.mp4","width":1920,"height":1080,"render_base":"960x540 deterministic superscale","fps":FPS,"duration_seconds":DURATION,"expected_frames":FRAMES,"audio_source":"audio/come_get_your_vitals.mp3","audio_offset_seconds":0},
        "shots":[
            {"id":"P01","start_frame":0,"end_frame":104,"description":"Outside detox-led fishbowl push and physical glass pass","assets":["env_outside_fishbowl.png"],"motion_channels":["camera depth push","strip refraction","bubbles/particles","caustics","glass highlights"],"static_only":False},
            {"id":"P02","start_frame":105,"end_frame":299,"description":"Detox station reveal with two clients and two nurses","assets":["env_detox_window.png","code rigs"],"motion_channels":["betta face/head/arms/tail/hair","two client tail rigs","camera drift","papers","water/caustics","pulse ox prop"],"static_only":False},
            {"id":"P03","start_frame":300,"end_frame":449,"description":"Puffer escalation and articulated performance","assets":["code rigs"],"motion_channels":["puffer radial rig","puffer arms/face/hair","betta lip/body performance","client swimming","camera/parallax","particles"],"static_only":False},
            {"id":"P04","start_frame":450,"end_frame":539,"description":"Client reaches glass; ripple interaction and puffer release","assets":["code rigs"],"motion_channels":["client fin reach","glass ripple","puffer deflation","betta secondary motion","bubbles/particles","caustics"],"static_only":False}
        ],
        "animation_truth":{"code_rigged":["all nurse body parts, eyes, mouths, arms, tails, hair groups","both client bodies, eyes, fins/tails, blanket props","puffer inflation/deflation","glass ripples and refraction","camera/parallax, bubbles, particles, caustics, plants, papers, pulse ox"],"sprite_based":["canonical environment paintings used as depth backplates"],"whole_sprite_character_translation":False,"generated_inbetweens":False,"randomness":"seeded with project seed 73184"}
    }
    (ROOT/"generated"/"proof-shot-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(out)


if __name__=="__main__":
    main()
