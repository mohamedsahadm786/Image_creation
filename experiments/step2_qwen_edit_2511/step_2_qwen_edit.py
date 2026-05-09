"""
step_2_qwen_edit.py — Step 2 product compositing via fal-ai/qwen-image-edit-2511.

Drop-in shape match for src/step_2_nano_banana.py:
  - Same product upload + cache pattern (reuses cache/fal_uploads.json)
  - Same image_urls order: [step_1_scene_url, product_url]
  - Same return-dict contract:
        local_path, fal_url, seed, request_id, elapsed_seconds, endpoint, cost_usd

Differences from Nano Banana caller:
  - Endpoint is fal-ai/qwen-image-edit-2511
  - Parameters: prompt + image_urls + image_size + num_images + enable_safety_checker
    (no aspect_ratio, no resolution, no enable_thinking — those are NB-specific)
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

FAL_ENDPOINT = "fal-ai/qwen-image-edit-2511"

# Reuse the same product image and same cache file the main pipeline uses,
# so we don't re-upload product.jpg redundantly.
PRODUCT_IMAGE_PATH = Path("assets/product.jpg")
UPLOAD_CACHE_PATH = Path("cache/fal_uploads.json")

COST_PER_IMAGE_USD = 0.04  # approximate

_product_url_cache: str | None = None


def _get_product_url() -> str:
    global _product_url_cache
    if _product_url_cache:
        return _product_url_cache

    UPLOAD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if UPLOAD_CACHE_PATH.exists():
        try:
            cache = json.loads(UPLOAD_CACHE_PATH.read_text())
            if "product_url" in cache:
                _product_url_cache = cache["product_url"]
                print(f"[step_2_qwen] using cached product url ({_product_url_cache[:60]}...)")
                return _product_url_cache
        except Exception:
            pass

    if not PRODUCT_IMAGE_PATH.exists():
        raise FileNotFoundError(f"product.jpg not found at {PRODUCT_IMAGE_PATH}")

    print(f"[step_2_qwen] uploading product.jpg to fal (one-time)")
    url = fal_client.upload_file(str(PRODUCT_IMAGE_PATH))
    _product_url_cache = url

    cache = {}
    if UPLOAD_CACHE_PATH.exists():
        try:
            cache = json.loads(UPLOAD_CACHE_PATH.read_text())
        except Exception:
            cache = {}
    cache["product_url"] = url
    UPLOAD_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    print(f"[step_2_qwen]   product url cached")
    return url


def generate(
    step_1_local_path: str,
    step_2_prompt: str,
    fal_qwen_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    """
    Run Qwen-Image-Edit-2511 on the persona scene + product reference.

    Args:
        step_1_local_path: filesystem path to 03_step1_persona.jpg
        step_2_prompt: the Opus-generated Step 2 prompt text
        fal_qwen_params: dict of Qwen-specific parameters (image_size, num_images, etc.)
        out_path: where to write the resulting JPG
        scenario_id: for logging

    Returns:
        dict with local_path, fal_url, seed, request_id, elapsed_seconds, endpoint, cost_usd
    """
    product_url = _get_product_url()

    print(f"[step_2_qwen] [{scenario_id}] uploading Step 1 scene to fal")
    step_1_url = fal_client.upload_file(step_1_local_path)

    # Same order as Nano Banana: scene first, product second.
    # The prompt refers to "the persona reference photo" (first) and
    # "the product reference photo" (second) per master_prompt_step2.md.
    image_urls = [step_1_url, product_url]

    arguments: dict = {
        "prompt": step_2_prompt,
        "image_urls": image_urls,
    }

    # Pass through Qwen-supported optional params if present in config
    if "image_size" in fal_qwen_params:
        arguments["image_size"] = fal_qwen_params["image_size"]
    if "num_images" in fal_qwen_params:
        arguments["num_images"] = fal_qwen_params["num_images"]
    if "output_format" in fal_qwen_params:
        arguments["output_format"] = fal_qwen_params["output_format"]
    if "enable_safety_checker" in fal_qwen_params:
        arguments["enable_safety_checker"] = fal_qwen_params["enable_safety_checker"]
    if "num_inference_steps" in fal_qwen_params:
        arguments["num_inference_steps"] = fal_qwen_params["num_inference_steps"]
    if "guidance_scale" in fal_qwen_params:
        arguments["guidance_scale"] = fal_qwen_params["guidance_scale"]
    if "acceleration" in fal_qwen_params:
        arguments["acceleration"] = fal_qwen_params["acceleration"]
    if "negative_prompt" in fal_qwen_params:
        arguments["negative_prompt"] = fal_qwen_params["negative_prompt"]

    img_size = arguments.get("image_size", "default")
    print(f"[step_2_qwen] [{scenario_id}] calling {FAL_ENDPOINT}")
    print(f"[step_2_qwen] [{scenario_id}]   image_size={img_size}")

    t0 = time.time()
    result = fal_client.subscribe(FAL_ENDPOINT, arguments=arguments, with_logs=False)
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(
            f"Qwen-Image-Edit-2511 returned no images for {scenario_id}. "
            f"Result keys: {list(result.keys())}"
        )

    image_url = images[0]["url"]
    seed = result.get("seed")
    request_id = result.get("request_id", "unknown")

    print(f"[step_2_qwen] [{scenario_id}]   composited in {elapsed:.1f}s, seed={seed}")

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