from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"assets"/"client-poses"


def background_mask(rgb: np.ndarray) -> np.ndarray:
    h,w,_=rgb.shape
    yy,xx=np.mgrid[0:h,0:w]
    border=np.zeros((h,w),dtype=bool)
    bw=max(8,min(h,w)//24)
    border[:bw]=True; border[-bw:]=True; border[:,:bw]=True; border[:,-bw:]=True
    # Reject unusually bright border intrusions before fitting the smooth teal plane.
    pix=rgb.astype(np.float32)
    chroma=np.max(pix,axis=2)-np.min(pix,axis=2)
    valid=border & (np.mean(pix,axis=2)<105) & (chroma<90)
    X=np.c_[xx[valid]/max(1,w-1),yy[valid]/max(1,h-1),np.ones(np.count_nonzero(valid))]
    coeff=np.linalg.lstsq(X,pix[valid],rcond=None)[0]
    allx=np.c_[xx.ravel()/max(1,w-1),yy.ravel()/max(1,h-1),np.ones(h*w)]
    predicted=(allx@coeff).reshape(h,w,3)
    diff=np.sqrt(np.sum((pix-predicted)**2,axis=2))
    raw=(diff>29).astype(np.uint8)*255
    mask=Image.fromarray(raw,"L").filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1.8))
    arr=np.array(mask)
    # Fade image borders to guarantee clean compositing between adjacent sheet cells.
    edge=np.minimum.reduce([xx,yy,w-1-xx,h-1-yy]).astype(np.float32)
    feather=np.clip(edge/10,0,1)
    return (arr.astype(np.float32)*feather).astype(np.uint8)


def extract(sheet: Image.Image,row:int,col:int)->Image.Image:
    w,h=sheet.size; x0=round(col*w/3); x1=round((col+1)*w/3); y0=round(row*h/5); y1=round((row+1)*h/5)
    crop=sheet.crop((x0,y0,x1,y1)).convert("RGB")
    rgb=np.array(crop)
    alpha=background_mask(rgb)
    rgba=np.dstack([rgb,alpha])
    out=Image.fromarray(rgba,"RGBA")
    bbox=out.getbbox()
    return out.crop(bbox) if bbox else out


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest={"schema_version":1,"states":["detox","stabilizing","residential"],"clients":{}}
    for sheet_i,name in enumerate(["client-concept-sheet-a.png","client-concept-sheet-b.png"]):
        sheet=Image.open(ROOT/"assets"/name)
        for row in range(5):
            client_num=sheet_i*5+row+1; cid=f"CLIENT_{client_num:02d}"; directory=OUT/cid; directory.mkdir(exist_ok=True)
            entries=[]
            for col,state in enumerate(manifest["states"]):
                pose=extract(sheet,row,col)
                path=directory/f"{state}.png"; pose.save(path)
                entries.append({"state":state,"file":str(path.relative_to(ROOT)).replace("\\","/"),"width":pose.width,"height":pose.height,"alpha_extrema":list(pose.getchannel("A").getextrema())})
            manifest["clients"][cid]=entries
    (ROOT/"generated/client-sprite-manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    # Produce a compact extraction QA board on a neutral checker-like field.
    board=Image.new("RGB",(1200,900),(19,53,61))
    for i,(cid,entries) in enumerate(manifest["clients"].items()):
        for j,e in enumerate(entries):
            art=Image.open(ROOT/e["file"]); scale=min(330/art.width,78/art.height); art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.LANCZOS)
            board.paste(art,(j*400+35,i*90+6),art)
    board.save(ROOT/"generated/client-sprite-extraction-board.jpg",quality=94)
    print(json.dumps({"clients":len(manifest["clients"]),"sprites":sum(len(v) for v in manifest["clients"].values())},indent=2))


if __name__=="__main__":main()
