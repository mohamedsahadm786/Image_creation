"""
step_1_kontext.py — Plan B Step 1 backup (fal-ai/flux-pro/kontext).

Used when Plan A's PuLID gives weak outfit-override results. This route
uses persona_face_only.jpg (manually cropped to face only — no outfit
visible) as the Kontext reference, which prevents Kontext from locking
the persona.jpg outfit.

Same return shape as step_1_pulid.generate() so the dispatcher can swap
between Plan A and Plan B with no downstream changes.
"""

import os
import json
import time
import requests
import fal_client
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("FAL_KEY"):
    raise RuntimeError("FAL_KEY not set in environment.")

FAL_ENDPOINT = "fal-ai/flux-pro/kontext"
FACE_IMAGE_PATH = Path("assets/persona_face_only.jpg")
UPLOAD_CACHE_PATH = Path("cache/fal_uploads.json")

COST_PER_IMAGE_USD = 0.04  # Kontext pro pricing

_face_url_cache: str | None = None


def _get_face_url() -> str:
    global _face_url_cache
    if _face_url_cache:
        return _face_url_cache

    UPLOAD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if UPLOAD_CACHE_PATH.exists():
        try:
            cache = json.loads(UPLOAD_CACHE_PATH.read_text())
            if "persona_face_url" in cache:
                _face_url_cache = cache["persona_face_url"]
                print(f"[step_1_kontext] using cached face url ({_face_url_cache[:60]}...)")
                return _face_url_cache
        except Exception:
            pass

    if not FACE_IMAGE_PATH.exists():
        raise FileNotFoundError(
            f"persona_face_only.jpg not found at {FACE_IMAGE_PATH}. "
            "Plan B requires a face-only crop. Crop persona.jpg to face only "
            "(no outfit visible) and save at this path."
        )

    print(f"[step_1_kontext] uploading persona_face_only.jpg to fal (one-time)")
    url = fal_client.upload_file(str(FACE_IMAGE_PATH))
    _face_url_cache = url

    cache = {}
    if UPLOAD_CACHE_PATH.exists():
        try:
            cache = json.loads(UPLOAD_CACHE_PATH.read_text())
        except Exception:
            cache = {}
    cache["persona_face_url"] = url
    UPLOAD_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    print(f"[step_1_kontext]   face url cached")
    return url


def generate(
    step_1_prompt: str,
    fal_kontext_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    face_url = _get_face_url()

    arguments = {
        "prompt": step_1_prompt,
        "image_url": face_url,
        "aspect_ratio": fal_kontext_params.get("aspect_ratio", "9:16"),
        "guidance_scale": fal_kontext_params.get("guidance_scale", 3.5),
        "num_inference_steps": fal_kontext_params.get("num_inference_steps", 30),
        "output_format": fal_kontext_params.get("output_format", "jpeg"),
    }

    print(f"[step_1_kontext] [{scenario_id}] calling {FAL_ENDPOINT}")
    print(f"[step_1_kontext] [{scenario_id}]   aspect_ratio={arguments['aspect_ratio']}")

    t0 = time.time()
    result = fal_client.subscribe(FAL_ENDPOINT, arguments=arguments, with_logs=False)
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(
            f"Kontext returned no images for {scenario_id}. Result keys: {list(result.keys())}"
        )

    image_url = images[0]["url"]
    seed = result.get("seed")
    request_id = result.get("request_id", "unknown")

    print(f"[step_1_kontext] [{scenario_id}]   generated in {elapsed:.1f}s, seed={seed}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(image_url, timeout=120)
    response.raise_for_status()
    out_path.write_bytes(response.content)

    return {
        "local_path": str(out_path),
        "fal_url": image_url,
        "seed": seed,
        "request_id": request_id,
        "elapsed_seconds": elapsed,
        "endpoint": FAL_ENDPOINT,
        "cost_usd": COST_PER_IMAGE_USD,
    }