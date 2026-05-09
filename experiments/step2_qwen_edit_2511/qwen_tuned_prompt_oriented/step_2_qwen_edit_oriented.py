"""
step_2_qwen_edit_oriented.py — self-contained Qwen API caller for the
qwen_tuned_prompt_oriented experiment.

Why this file exists separately from the parent's step_2_qwen_edit.py:
The parent caller hardcodes the product reference path to assets/product.jpg.
This experiment needs to pass a different file (product_horizontal.jpg /
product_vertical.jpg / product_45_right.jpg / product_45_left.jpg) per
scenario. Rather than modifying the parent (which is in active use by
other experiments), this experiment ships its own caller that takes
product_local_path as a parameter.

Reuses the shared cache/fal_uploads.json — different orientation files
get different cache keys naturally (cached by absolute path), so this
experiment's uploads don't collide with the parent's.

Environment requirements:
- FAL_KEY in .env
- fal-client and httpx installed
"""

import os
import json
import time
from pathlib import Path

import fal_client
import httpx
from dotenv import load_dotenv

load_dotenv()

# Project root: from
#   experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/step_2_qwen_edit_oriented.py
# go up 3 levels.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = PROJECT_ROOT / "cache" / "fal_uploads.json"

QWEN_ENDPOINT = "fal-ai/qwen-image-edit-2511"


def _ensure_fal_key() -> None:
    if not os.getenv("FAL_KEY"):
        raise RuntimeError("FAL_KEY not set in environment (.env)")


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _upload_with_cache(local_path: str) -> str:
    """
    Upload file to fal once and cache the URL keyed by absolute path.
    Different orientation files have different absolute paths so they
    each get their own cache entry — no collision with parent experiments.
    """
    _ensure_fal_key()
    abs_path = str(Path(local_path).resolve())

    cache = _load_cache()
    if abs_path in cache and isinstance(cache[abs_path], str):
        return cache[abs_path]

    print(f"[step_2_qwen_oriented] uploading: {abs_path}")
    url = fal_client.upload_file(abs_path)
    cache[abs_path] = url
    _save_cache(cache)
    return url


def generate_with_product(
    persona_local_path: str,
    product_local_path: str,
    prompt: str,
    fal_qwen_params: dict,
    out_path: Path,
    scenario_id: str,
) -> dict:
    """
    Run Qwen-Image-Edit-2511 with persona (image_urls[0]) and a specific
    product reference (image_urls[1]).

    Args:
        persona_local_path: path to Step 1 output image (the persona scene)
        product_local_path: path to the chosen pre-rotated product image
                            (assets/product_horizontal.jpg or _vertical.jpg
                             or _45_right.jpg or _45_left.jpg)
        prompt: the step_2_image_prompt string
        fal_qwen_params: dict from config.yaml (image_size, num_images,
                         output_format, enable_safety_checker)
        out_path: where to write the result image
        scenario_id: for logging

    Returns:
        dict with metadata: endpoint, seed, elapsed_seconds, image_url,
        persona_url, product_url, product_local_path, fal_qwen_params.
    """
    _ensure_fal_key()

    persona_url = _upload_with_cache(persona_local_path)
    product_url = _upload_with_cache(product_local_path)

    arguments = {
        "image_urls": [persona_url, product_url],
        "prompt": prompt,
        **fal_qwen_params,
    }

    print(f"[step_2_qwen_oriented] {scenario_id}: calling {QWEN_ENDPOINT}")
    print(f"[step_2_qwen_oriented]   product file: {Path(product_local_path).name}")

    t0 = time.time()
    result = fal_client.subscribe(
        QWEN_ENDPOINT,
        arguments=arguments,
        with_logs=False,
    )
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"qwen returned no images for {scenario_id}: {result}")

    image_url = images[0].get("url")
    if not image_url:
        raise RuntimeError(f"qwen image entry missing url for {scenario_id}: {images[0]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(image_url, timeout=120)
    response.raise_for_status()
    out_path.write_bytes(response.content)

    print(f"[step_2_qwen_oriented]   done in {elapsed:.1f}s, wrote {out_path}")

    return {
        "endpoint": QWEN_ENDPOINT,
        "seed": result.get("seed"),
        "elapsed_seconds": round(elapsed, 1),
        "image_url": image_url,
        "persona_url": persona_url,
        "product_url": product_url,
        "product_local_path": str(Path(product_local_path).resolve()),
        "fal_qwen_params": fal_qwen_params,
    }