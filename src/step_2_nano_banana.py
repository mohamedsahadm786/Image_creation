"""
step_2_nano_banana.py — Step 2 product compositing (fal-ai/nano-banana-2/edit).

Takes the Step 1 image and the product reference, and produces the final
composite with the actual Alluvi product naturally placed in the scene.

No mask needed. Nano Banana 2 handles compositing natively from references.
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

FAL_ENDPOINT = "fal-ai/nano-banana-2/edit"
PRODUCT_IMAGE_PATH = Path("assets/product.jpg")
UPLOAD_CACHE_PATH = Path("cache/fal_uploads.json")

COST_PER_IMAGE_USD = 0.04  # base; +$0.015 if web search enabled (we don't use it)

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
                print(f"[step_2] using cached product url ({_product_url_cache[:60]}...)")
                return _product_url_cache
        except Exception:
            pass

    if not PRODUCT_IMAGE_PATH.exists():
        raise FileNotFoundError(f"product.jpg not found at {PRODUCT_IMAGE_PATH}")

    print(f"[step_2] uploading product.jpg to fal (one-time)")
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
    print(f"[step_2]   product url cached")
    return url


def generate(
    step_1_local_path: str,
    step_2_prompt: str,
    fal_nano_banana_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    product_url = _get_product_url()

    print(f"[step_2] [{scenario_id}] uploading Step 1 scene to fal")
    step_1_url = fal_client.upload_file(step_1_local_path)

    # Image 1 = scene, Image 2 = product (matches the prompt's reference syntax)
    image_urls = [step_1_url, product_url]

    arguments = {
        "prompt": step_2_prompt,
        "image_urls": image_urls,
        "aspect_ratio": fal_nano_banana_params.get("aspect_ratio", "9:16"),
        "resolution": fal_nano_banana_params.get("resolution", "1K"),
        "num_images": fal_nano_banana_params.get("num_images", 1),
        "output_format": fal_nano_banana_params.get("output_format", "png"),
        "safety_tolerance": fal_nano_banana_params.get("safety_tolerance", "4"),
    }

    # enable_thinking is a Nano Banana 2 feature that improves multi-image compositing
    if fal_nano_banana_params.get("enable_thinking"):
        arguments["enable_thinking"] = fal_nano_banana_params["enable_thinking"]

    print(f"[step_2] [{scenario_id}] calling {FAL_ENDPOINT}")
    print(f"[step_2] [{scenario_id}]   aspect_ratio={arguments['aspect_ratio']} resolution={arguments['resolution']}")

    t0 = time.time()
    result = fal_client.subscribe(FAL_ENDPOINT, arguments=arguments, with_logs=False)
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(
            f"Nano Banana 2 Edit returned no images for {scenario_id}. "
            f"Result keys: {list(result.keys())}"
        )

    image_url = images[0]["url"]
    seed = result.get("seed")
    request_id = result.get("request_id", "unknown")

    print(f"[step_2] [{scenario_id}]   composited in {elapsed:.1f}s, seed={seed}")

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