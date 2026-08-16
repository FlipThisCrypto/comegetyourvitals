from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "poses"
REGISTRY = json.loads((ROOT / "character-registry.json").read_text(encoding="utf-8"))


def component_keep(im: Image.Image) -> Image.Image:
    rgba = im.convert("RGBA")
    alpha = np.array(rgba.getchannel("A")) > 14
    h, w = alpha.shape
    seen = np.zeros_like(alpha, dtype=bool)
    comps: list[list[tuple[int, int]]] = []
    for y in range(h):
        for x in range(w):
            if not alpha[y, x] or seen[y, x]:
                continue
            stack = [(x, y)]; seen[y, x] = True; pts = []
            while stack:
                cx, cy = stack.pop(); pts.append((cx, cy))
                for nx, ny in ((cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)):
                    if 0 <= nx < w and 0 <= ny < h and alpha[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx] = True; stack.append((nx,ny))
            if len(pts) > 80:
                comps.append(pts)
    comps.sort(key=len, reverse=True)
    keep = np.zeros_like(alpha)
    # Preserve the hero body and nearby connected prop/bubble pieces.
    for pts in comps[:4]:
        if len(pts) < (len(comps[0]) * .018 if comps else 0):
            continue
        xs = np.fromiter((p[0] for p in pts), dtype=np.int32)
        ys = np.fromiter((p[1] for p in pts), dtype=np.int32)
        keep[ys, xs] = True
    arr = np.array(rgba)
    arr[..., 3] = np.where(keep, arr[..., 3], 0)
    clean = Image.fromarray(arr, "RGBA")
    bbox = clean.getbbox()
    return clean.crop(bbox) if bbox else clean


def cells(im: Image.Image, cols: int, rows: int):
    cw, ch = im.width / cols, im.height / rows
    for row in range(rows):
        for col in range(cols):
            pad_x, pad_y = cw*.13, ch*.10
            box = (
                max(0, round(col*cw-pad_x)), max(0, round(row*ch-pad_y)),
                min(im.width, round((col+1)*cw+pad_x)), min(im.height, round((row+1)*ch+pad_y)),
            )
            yield row, col, component_keep(im.crop(box))


def main():
    manifest = {"schema_version": 1, "characters": {}}
    for nurse in REGISTRY["nurses"]:
        cid = nurse["id"]
        source = ROOT / nurse["asset"]
        im = Image.open(source).convert("RGBA")
        cols, rows = (4, 3) if cid == "NURSE_PUFFER" else (5, 2)
        directory = OUT / cid
        directory.mkdir(parents=True, exist_ok=True)
        poses = []
        for row, col, crop in cells(im, cols, rows):
            if crop.width < 70 or crop.height < 70:
                continue
            pose_id = f"pose_{len(poses):02d}"
            path = directory / f"{pose_id}.png"
            crop.save(path)
            poses.append({
                "id": pose_id, "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "source_cell": [row, col], "width": crop.width, "height": crop.height,
                "alpha_bbox": list(crop.getbbox()),
            })
        manifest["characters"][cid] = {
            "source": str(source.relative_to(ROOT)).replace("\\", "/"),
            "poses": poses,
            "canonical_colors": nurse["primary_colors"],
            "identifying_feature": nurse["identifying_feature"],
        }
    (ROOT / "generated").mkdir(exist_ok=True)
    (ROOT / "generated" / "pose-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: len(v["poses"]) for k,v in manifest["characters"].items()}, indent=2))


if __name__ == "__main__":
    main()
