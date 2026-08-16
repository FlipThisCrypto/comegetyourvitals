#!/usr/bin/env python3
"""Render a resumable set of Flux Kontext production keyframes."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from flux_kontext_edit import api_json, prompt_graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    jobs = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.destination.mkdir(parents=True, exist_ok=True)
    for index, job in enumerate(jobs, 1):
        destination = args.destination / f"{job['name']}.png"
        if destination.is_file():
            print(json.dumps({"resume": job["name"], "index": index, "total": len(jobs)}), flush=True)
            continue
        graph = prompt_graph(
            job["source"], job["prompt"], int(job["seed"]),
            f"cgyv/full60/{job['name']}", list(job.get("references", [])),
        )
        queued = api_json(args.endpoint, "/prompt", {"prompt": graph})
        prompt_id = queued["prompt_id"]
        print(json.dumps({"queued": job["name"], "prompt_id": prompt_id, "index": index, "total": len(jobs)}), flush=True)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            history = api_json(args.endpoint, f"/history/{prompt_id}")
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(json.dumps({"job": job["name"], "status": status}, indent=2))
                images = entry.get("outputs", {}).get("13", {}).get("images", [])
                if images:
                    item = images[0]
                    source = args.output_root / item.get("subfolder", "") / item["filename"]
                    shutil.copy2(source, destination)
                    print(json.dumps({"complete": job["name"], "path": str(destination)}), flush=True)
                    break
            time.sleep(2)
        else:
            raise TimeoutError(f"Keyframe {job['name']} exceeded {args.timeout} seconds")


if __name__ == "__main__":
    main()
