#!/usr/bin/env python3
"""Run a reproducible Flux Kontext image edit through a local ComfyUI API."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.request
from pathlib import Path


def api_json(endpoint: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def prompt_graph(
    image_name: str,
    prompt: str,
    seed: int,
    prefix: str,
    reference_names: list[str] | None = None,
) -> dict:
    graph = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux1-kontext-dev-Q4_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": "clip_l.safetensors",
            "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
            "type": "flux",
            "device": "default",
        }},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "5": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["4", 0]}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "8": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}},
        "9": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["8", 0], "guidance": 2.5}},
        "10": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "11": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": seed, "steps": 20, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["9", 0], "negative": ["10", 0],
            "latent_image": ["6", 0], "denoise": 1.0,
        }},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": prefix}},
    }
    conditioning_node = "8"
    for index, reference_name in enumerate(reference_names or []):
        load_id = str(20 + index * 4)
        scale_id = str(21 + index * 4)
        encode_id = str(22 + index * 4)
        reference_id = str(23 + index * 4)
        graph[load_id] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
        graph[scale_id] = {"class_type": "FluxKontextImageScale", "inputs": {"image": [load_id, 0]}}
        graph[encode_id] = {"class_type": "VAEEncode", "inputs": {"pixels": [scale_id, 0], "vae": ["3", 0]}}
        graph[reference_id] = {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": [conditioning_node, 0], "latent": [encode_id, 0]},
        }
        conditioning_node = reference_id
    graph["9"]["inputs"]["conditioning"] = [conditioning_node, 0]
    return graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image_name", help="Filename already present in the ComfyUI input directory")
    parser.add_argument("prompt", nargs="?", help="Edit instruction (or use --prompt-file)")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=680407)
    parser.add_argument("--prefix", default="cgyv/kontext")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--reference-name", action="append", default=[])
    args = parser.parse_args()

    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    elif args.prompt:
        prompt = args.prompt
    else:
        parser.error("provide a prompt or --prompt-file")

    queued = api_json(
        args.endpoint,
        "/prompt",
        {"prompt": prompt_graph(args.image_name, prompt, args.seed, args.prefix, args.reference_name)},
    )
    prompt_id = queued["prompt_id"]
    print(json.dumps({"queued": prompt_id}), flush=True)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        history = api_json(args.endpoint, f"/history/{prompt_id}")
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status, indent=2))
            images = entry.get("outputs", {}).get("13", {}).get("images", [])
            if images:
                item = images[0]
                source = args.output_root / item.get("subfolder", "") / item["filename"]
                args.destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, args.destination)
                print(json.dumps({"complete": str(args.destination), "source": str(source)}), flush=True)
                return
        time.sleep(2)
    raise TimeoutError(f"Flux Kontext edit exceeded {args.timeout} seconds")


if __name__ == "__main__":
    main()
