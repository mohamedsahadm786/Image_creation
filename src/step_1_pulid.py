"""
step_1_pulid.py — Plan A Step 1 image generation (fal-ai/flux-pulid).

Generates persona scene with scenario-specific outfit. NO product. The
product hand is empty in the output, ready for Step 2 to composite into.

Inputs:
  - step_1_prompt   : the prompt string from prompt_builder.build_step_1_prompt
  - fal_pulid_params: dict with image_size, id_weight, true_cfg, etc.
  - out_path        : where to save the generated image

Returns: dict with local_path, fal_url, seed, request_id, elapsed_seconds
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

FAL_ENDPOINT = "fal-ai/flux-pulid"
PERSONA_IMAGE_PATH = Path("assets/persona.jpg")
UPLOAD_CACHE_PATH = Path("cache/fal_uploads.json")

# Plan A cost estimate (used for run accounting)
COST_PER_IMAGE_USD = 0.04

_persona_url_cache: str | None = None


def _get_persona_url() -> str:
    """Upload persona.jpg to fal once per process; persist URL across runs."""
    global _persona_url_cache
    if _persona_url_cache:
        return _persona_url_cache

    UPLOAD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if UPLOAD_CACHE_PATH.exists():
        try:
            cache = json.loads(UPLOAD_CACHE_PATH.read_text())
            if "persona_url" in cache:
                _persona_url_cache = cache["persona_url"]
                print(f"[step_1_pulid] using cached persona url ({_persona_url_cache[:60]}...)")
                return _persona_url_cache
        except Exception:
            pass

    if not PERSONA_IMAGE_PATH.exists():
        raise FileNotFoundError(f"persona.jpg not found at {PERSONA_IMAGE_PATH}")

    print(f"[step_1_pulid] uploading persona.jpg to fal (one-time)")
    url = fal_client.upload_file(str(PERSONA_IMAGE_PATH))
    _persona_url_cache = url

    cache = {}
    if UPLOAD_CACHE_PATH.exists():
        try:
            cache = json.loads(UPLOAD_CACHE_PATH.read_text())
        except Exception:
            cache = {}
    cache["persona_url"] = url
    UPLOAD_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    print(f"[step_1_pulid]   persona url cached")
    return url


def generate(
    step_1_prompt: str,
    fal_pulid_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    persona_url = _get_persona_url()

    img_size = fal_pulid_params.get("image_size", {"width": 768, "height": 1344})

    arguments = {
        "prompt": step_1_prompt,
        "reference_image_url": persona_url,
        "image_size": img_size,
        "num_inference_steps": fal_pulid_params.get("num_inference_steps", 30),
        "guidance_scale": fal_pulid_params.get("guidance_scale", 4.0),
        "id_weight": fal_pulid_params.get("id_weight", 1.0),
        "true_cfg": fal_pulid_params.get("true_cfg", 1.5),
        "max_sequence_length": fal_pulid_params.get("max_sequence_length", "256"),
        "enable_safety_checker": fal_pulid_params.get("enable_safety_checker", True),
    }

    if fal_pulid_params.get("negative_prompt"):
        arguments["negative_prompt"] = fal_pulid_params["negative_prompt"]

    print(f"[step_1_pulid] [{scenario_id}] calling {FAL_ENDPOINT}")
    print(f"[step_1_pulid] [{scenario_id}]   id_weight={arguments['id_weight']} steps={arguments['num_inference_steps']}")

    t0 = time.time()
    result = fal_client.subscribe(FAL_ENDPOINT, arguments=arguments, with_logs=False)
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(
            f"PuLID returned no images for {scenario_id}. Result keys: {list(result.keys())}"
        )

    image_url = images[0]["url"]
    seed = result.get("seed")
    request_id = result.get("request_id", "unknown")

    print(f"[step_1_pulid] [{scenario_id}]   generated in {elapsed:.1f}s, seed={seed}")

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