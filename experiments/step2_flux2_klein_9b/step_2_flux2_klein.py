"""
step_2_flux2_klein.py — Step 2 product compositing via fal-ai/flux-2/klein/9b/edit.

Drop-in shape match for the parallel Qwen + Nano Banana callers:
  - Same product upload + cache pattern (reuses cache/fal_uploads.json — same
    cache as the main pipeline + the Qwen experiment, since it's the same
    product reference image)
  - Same image_urls order: [step_1_scene_url, product_url]
  - Same return-dict contract:
        local_path, fal_url, seed, request_id, elapsed_seconds, endpoint, cost_usd

Differences from Qwen caller:
  - Endpoint: fal-ai/flux-2/klein/9b/edit (distilled 9B Edit, 4-step inference)
  - Parameters: prompt, image_urls, image_size, num_images, enable_safety_checker,
    output_format, negative_prompt, seed
  - num_inference_steps is fixed at 4 by the distilled endpoint and is NOT passed.
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

FAL_ENDPOINT = "fal-ai/flux-2/klein/9b/edit"

# Reuse the same product image and same cache file the main pipeline uses,
# so we don't re-upload product.jpg redundantly.
PRODUCT_IMAGE_PATH = Path("assets/product.jpg")
UPLOAD_CACHE_PATH = Path("cache/fal_uploads.json")

COST_PER_IMAGE_USD = 0.025  # approximate; verify on fal pricing for actual billing

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
                print(f"[step_2_flux2] using cached product url ({_product_url_cache[:60]}...)")
                return _product_url_cache
        except Exception:
            pass

    if not PRODUCT_IMAGE_PATH.exists():
        raise FileNotFoundError(f"product.jpg not found at {PRODUCT_IMAGE_PATH}")

    print(f"[step_2_flux2] uploading product.jpg to fal (one-time)")
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
    print(f"[step_2_flux2]   product url cached")
    return url


def generate(
    step_1_local_path: str,
    step_2_prompt: str,
    fal_flux2_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    """
    Run FLUX-2-Klein-9B Edit on the persona scene + product reference.

    Args:
        step_1_local_path: filesystem path to 03_step1_persona.jpg
        step_2_prompt: the Opus-generated Step 2 prompt text
        fal_flux2_params: dict of FLUX-specific parameters (image_size, etc.)
        out_path: where to write the resulting image
        scenario_id: for logging

    Returns:
        dict with local_path, fal_url, seed, request_id, elapsed_seconds, endpoint, cost_usd
    """
    product_url = _get_product_url()

    print(f"[step_2_flux2] [{scenario_id}] uploading Step 1 scene to fal")
    step_1_url = fal_client.upload_file(step_1_local_path)

    # Same order as Nano Banana and Qwen: scene first, product second.
    image_urls = [step_1_url, product_url]

    arguments: dict = {
        "prompt": step_2_prompt,
        "image_urls": image_urls,
    }

    # Pass through FLUX-2-Klein-supported optional params if present in config
    if "image_size" in fal_flux2_params:
        arguments["image_size"] = fal_flux2_params["image_size"]
    if "num_images" in fal_flux2_params:
        arguments["num_images"] = fal_flux2_params["num_images"]
    if "output_format" in fal_flux2_params:
        arguments["output_format"] = fal_flux2_params["output_format"]
    if "enable_safety_checker" in fal_flux2_params:
        arguments["enable_safety_checker"] = fal_flux2_params["enable_safety_checker"]
    if "negative_prompt" in fal_flux2_params:
        arguments["negative_prompt"] = fal_flux2_params["negative_prompt"]
    if "seed" in fal_flux2_params:
        arguments["seed"] = fal_flux2_params["seed"]

    img_size = arguments.get("image_size", "default")
    print(f"[step_2_flux2] [{scenario_id}] calling {FAL_ENDPOINT}")
    print(f"[step_2_flux2] [{scenario_id}]   image_size={img_size}")

    t0 = time.time()
    result = fal_client.subscribe(FAL_ENDPOINT, arguments=arguments, with_logs=False)
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(
            f"FLUX-2-Klein-9B Edit returned no images for {scenario_id}. "
            f"Result keys: {list(result.keys())}"
        )

    image_url = images[0]["url"]
    seed = result.get("seed")
    request_id = result.get("request_id", "unknown")

    print(f"[step_2_flux2] [{scenario_id}]   composited in {elapsed:.1f}s, seed={seed}")

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