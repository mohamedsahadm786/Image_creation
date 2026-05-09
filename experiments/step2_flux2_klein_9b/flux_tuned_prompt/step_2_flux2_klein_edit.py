"""
step_2_flux2_klein_edit.py — self-contained FLUX-2 Klein 9B Base Edit caller
for the flux_tuned_prompt experiment.

Calls fal-ai/flux-2/klein/9b/base/edit (NOT the distilled 9b/edit). The Base
variant supports negative_prompt and guidance_scale via classifier-free
guidance — both required for our FLUX-tuned prompt approach.

Endpoint comparison:
  9b/edit       — distilled, 4 steps, NO CFG, NO negative_prompt, ~$0.025/img
  9b/base/edit  — base, 28 steps, supports CFG + negative_prompt, ~$0.05/img  ← us

Reuses the shared cache/fal_uploads.json — different orientation files
(or the single product.jpg in this experiment) get different cache keys
naturally, so this experiment's uploads don't collide with parent or
sibling experiments.

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
#   experiments/step2_flux2_klein_9b/flux_tuned_prompt/step_2_flux2_klein_edit.py
# go up 3 levels.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = PROJECT_ROOT / "cache" / "fal_uploads.json"

FLUX_ENDPOINT = "fal-ai/flux-2/klein/9b/base/edit"


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
    """Upload file to fal once and cache the URL keyed by absolute path."""
    _ensure_fal_key()
    abs_path = str(Path(local_path).resolve())

    cache = _load_cache()
    if abs_path in cache and isinstance(cache[abs_path], str):
        return cache[abs_path]

    print(f"[step_2_flux] uploading: {abs_path}")
    url = fal_client.upload_file(abs_path)
    cache[abs_path] = url
    _save_cache(cache)
    return url


def generate(
    persona_local_path: str,
    product_local_path: str,
    prompt: str,
    negative_prompt: str,
    fal_flux_params: dict,
    out_path: Path,
    scenario_id: str,
) -> dict:
    """
    Run FLUX-2 Klein 9B Base Edit with persona (image_urls[0]) and product
    (image_urls[1]) reference images.

    Args:
        persona_local_path: path to Step 1 output image (the persona scene)
        product_local_path: path to product reference image (assets/product.jpg)
        prompt: the step_2_image_prompt string (180-260 words)
        negative_prompt: the focused negative prompt string
        fal_flux_params: dict from config.yaml or prompt envelope
                         (image_size, guidance_scale, num_inference_steps,
                          num_images, output_format, enable_safety_checker)
        out_path: where to write the result image
        scenario_id: for logging

    Returns:
        dict with metadata: endpoint, seed, elapsed_seconds, image_url,
        persona_url, product_url, fal_flux_params, prompt, negative_prompt.
    """
    _ensure_fal_key()

    persona_url = _upload_with_cache(persona_local_path)
    product_url = _upload_with_cache(product_local_path)

    # Build arguments dict.
    # Per fal's 9b/base/edit API schema: prompt, image_urls (max 4),
    # negative_prompt (default ""), guidance_scale (default 5),
    # num_inference_steps (default 28), seed, image_size, num_images,
    # acceleration, enable_safety_checker, output_format
    arguments = {
        "prompt": prompt,
        "image_urls": [persona_url, product_url],
    }
    if negative_prompt and negative_prompt.strip():
        arguments["negative_prompt"] = negative_prompt
    arguments.update(fal_flux_params)

    print(f"[step_2_flux] {scenario_id}: calling {FLUX_ENDPOINT}")
    print(f"[step_2_flux]   product file: {Path(product_local_path).name}")
    print(f"[step_2_flux]   guidance_scale: {arguments.get('guidance_scale', '?')}")
    print(f"[step_2_flux]   num_inference_steps: {arguments.get('num_inference_steps', '?')}")
    print(f"[step_2_flux]   negative_prompt: {'present' if 'negative_prompt' in arguments else 'absent'}")

    t0 = time.time()
    result = fal_client.subscribe(
        FLUX_ENDPOINT,
        arguments=arguments,
        with_logs=False,
    )
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"FLUX returned no images for {scenario_id}: {result}")

    image_url = images[0].get("url")
    if not image_url:
        raise RuntimeError(f"FLUX image entry missing url for {scenario_id}: {images[0]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(image_url, timeout=180)
    response.raise_for_status()
    out_path.write_bytes(response.content)

    print(f"[step_2_flux]   done in {elapsed:.1f}s, wrote {out_path}")

    return {
        "endpoint": FLUX_ENDPOINT,
        "seed": result.get("seed"),
        "elapsed_seconds": round(elapsed, 1),
        "image_url": image_url,
        "persona_url": persona_url,
        "product_url": product_url,
        "product_local_path": str(Path(product_local_path).resolve()),
        "fal_flux_params": fal_flux_params,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
    }