"""
experiments/step2_flux2_klein_9b/flux_tuned_prompt/batch_runner/run_batch_full.py

FULL FROM-SCRATCH batch runner for the flux_tuned_prompt experiment.

Unlike run_batch.py (which reuses Stage 1 + NB outputs from a prior Plan A
run for A/B comparison), this runner generates EVERYTHING from scratch:

  1. Step 1 prompt — Opus 4.7 + project's prompts/master_prompt_step1.md
  2. Stage 1 image — fal-ai/flux-pulid using assets/persona.jpg + Step 1 prompt
  3. Step 2 prompt — Opus 4.7 + this experiment's master_prompt_step2_flux.md
                     (FLUX-tuned: 180-260 word budget, negative_prompt,
                      camera/lens spec, guidance_scale 6.0)
  4. Stage 2 image — fal-ai/flux-2/klein/9b/base/edit with persona +
                     assets/product.jpg (single product, no orientation logic)

Per-scenario output:
  01_scenario.yaml
  02_step1_prompt.json          (NEW — fresh from Opus)
  03_step1_persona.jpg          (NEW — fresh from PuLID)
  03_step1_meta.json            (NEW — PuLID meta)
  04_step2_flux_prompt.json     (NEW — fresh from Opus, FLUX-tuned)
  05_step2_flux.jpg             (NEW — fresh from FLUX 9B Base Edit)
  05_step2_flux_meta.json
  chain.html                    (3-panel: Step 0 / Step 1 / FLUX, orange accent)

Batch output:
  experiments/step2_flux2_klein_9b/flux_tuned_prompt/batch_runner/outputs/<timestamp>_full/
    overview.html               (single-card grid, FLUX-tuned with orange accent)
    batch_manifest.json
    <scenario_id>/
      ...

Per-scenario cost (estimate):
  $0.10  PuLID Stage 1 (fal API)
  $0.10  Step 1 prompt (Opus)
  $0.15  Step 2 prompt (Opus, ~250 words)
  $0.05  FLUX-2 Klein 9B Base Edit (fal API)
  ─────
  $0.40  per scenario  → ~$12.00 for 30 scenarios

Wall time: ~30-40s per scenario sequential → ~15-20 min for 30 scenarios.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full

    # or with filters:
    python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full --only bedroom_robe_with_product_13

    # or skip cost confirmation:
    python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full --yes
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Project root: 4 levels up from
#   experiments/step2_flux2_klein_9b/flux_tuned_prompt/batch_runner/run_batch_full.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# This experiment's modules
from experiments.step2_flux2_klein_9b.flux_tuned_prompt import prompt_builder_flux
from experiments.step2_flux2_klein_9b.flux_tuned_prompt import step_2_flux2_klein_edit
from experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner import (
    trace_html_batch as batch_trace,
)

import fal_client
import httpx
from anthropic import Anthropic


# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
BATCH_OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"

STEP_1_MASTER_PROMPT = PROJECT_ROOT / "prompts" / "master_prompt_step1.md"

PERSONA_JPG = PROJECT_ROOT / "assets" / "persona.jpg"
PERSONA_YAML = PROJECT_ROOT / "assets" / "persona.yaml"
PRODUCT_JPG = PROJECT_ROOT / "assets" / "product.jpg"
PRODUCT_YAML = PROJECT_ROOT / "assets" / "product.yaml"
BRAND_YAML = PROJECT_ROOT / "brand" / "brand.yaml"
DO_DONT_MD = PROJECT_ROOT / "brand" / "do_dont.md"
SCENARIOS_YAML = PROJECT_ROOT / "scenarios" / "scenarios.yaml"

CACHE_PATH = PROJECT_ROOT / "cache" / "fal_uploads.json"


# ──────────────────────────────────────────────────────────────────────────
# Constants & cost model
# ──────────────────────────────────────────────────────────────────────────

CLAUDE_MODEL = "claude-opus-4-7"
PULID_ENDPOINT = "fal-ai/flux-pulid"

EXPERIMENT_NAME = "step2_flux2_klein_9b_with_flux_tuned_prompt_FROM_SCRATCH"

COST_PULID_USD = 0.10
COST_OPUS_STEP1_USD = 0.10  # estimate
COST_OPUS_STEP2_USD = 0.15  # FLUX prompts are shorter than Qwen, slightly cheaper
COST_FLUX_USD = 0.05        # 9b/base/edit ~$0.05/img
COST_PER_SCENARIO_USD = (
    COST_PULID_USD + COST_OPUS_STEP1_USD + COST_OPUS_STEP2_USD + COST_FLUX_USD
)

# Default PuLID params — override by adding `step_1.defaults` in config.yaml
DEFAULT_PULID_PARAMS = {
    "image_size": {"width": 768, "height": 1344},
    "num_inference_steps": 28,
    "guidance_scale": 4.0,
    "true_cfg": 1.0,
    "id_weight": 1.0,
    "max_sequence_length": 128,
    "num_images": 1,
    "output_format": "jpeg",
    "enable_safety_checker": True,
}


# ──────────────────────────────────────────────────────────────────────────
# Anthropic client (Step 1 prompt builder uses this)
# ──────────────────────────────────────────────────────────────────────────

_anthropic_client: Anthropic | None = None


def _get_anthropic_client() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment (.env)")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


# ──────────────────────────────────────────────────────────────────────────
# Step 1 prompt builder — self-contained
# ──────────────────────────────────────────────────────────────────────────

def build_step_1_prompt(scenario: dict) -> dict:
    """
    Build the Step 1 prompt envelope using the project's
    prompts/master_prompt_step1.md as the system prompt.

    Self-contained replica of what src/prompt_builder.py does for Step 1.
    Reads but never modifies the project's master prompt.
    """
    if not STEP_1_MASTER_PROMPT.exists():
        raise FileNotFoundError(
            f"missing project Step 1 master prompt: {STEP_1_MASTER_PROMPT}"
        )

    paths_to_load = {
        "persona_yaml": PERSONA_YAML,
        "product_yaml": PRODUCT_YAML,
        "brand_yaml": BRAND_YAML,
        "do_dont_md": DO_DONT_MD,
    }
    missing = [p for p in paths_to_load.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing static context files (must run from project root):\n  "
            + "\n  ".join(str(p) for p in missing)
        )

    system_prompt = STEP_1_MASTER_PROMPT.read_text(encoding="utf-8")
    static_ctx = {k: p.read_text(encoding="utf-8") for k, p in paths_to_load.items()}

    user_message = "\n".join(
        [
            "=== persona.yaml (use prompt_descriptors VERBATIM — never paraphrase) ===",
            static_ctx["persona_yaml"],
            "",
            "=== product.yaml (INTERNAL VALIDATION ONLY — never describe in prompt) ===",
            static_ctx["product_yaml"],
            "",
            "=== brand.yaml ===",
            static_ctx["brand_yaml"],
            "",
            "=== do_dont.md (compliance) ===",
            static_ctx["do_dont_md"],
            "",
            "=== SCENARIO ===",
            json.dumps(scenario, indent=2),
            "",
            "=== TASK ===",
            "Build the Step 1 prompt envelope per the system prompt above.",
            "Output JSON only. No preamble. No markdown fences.",
        ]
    )

    print(f"[step_1_prompt] -> Opus 4.7 for scenario {scenario.get('id', '?')}")
    response = _get_anthropic_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return _parse_json(response.content[0].text)


# ──────────────────────────────────────────────────────────────────────────
# PuLID caller — self-contained
# ──────────────────────────────────────────────────────────────────────────

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
    _ensure_fal_key()
    abs_path = str(Path(local_path).resolve())
    cache = _load_cache()
    if abs_path in cache and isinstance(cache[abs_path], str):
        return cache[abs_path]
    print(f"[step_1_pulid] uploading: {abs_path}")
    url = fal_client.upload_file(abs_path)
    cache[abs_path] = url
    _save_cache(cache)
    return url


def run_pulid_step1(
    step_1_prompt_text: str,
    persona_local_path: str,
    fal_pulid_params: dict,
    out_path: Path,
    scenario_id: str,
) -> dict:
    """Run fal-ai/flux-pulid with persona reference + Step 1 prompt."""
    _ensure_fal_key()
    persona_url = _upload_with_cache(persona_local_path)

    arguments = {
        "prompt": step_1_prompt_text,
        "reference_image_url": persona_url,
        **fal_pulid_params,
    }

    print(f"[step_1_pulid] {scenario_id}: calling {PULID_ENDPOINT}")
    t0 = time.time()
    result = fal_client.subscribe(
        PULID_ENDPOINT, arguments=arguments, with_logs=False
    )
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"PuLID returned no images for {scenario_id}: {result}")

    image_url = images[0].get("url")
    if not image_url:
        raise RuntimeError(f"PuLID image entry missing url for {scenario_id}: {images[0]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(image_url, timeout=180)
    response.raise_for_status()
    out_path.write_bytes(response.content)

    print(f"[step_1_pulid]   done in {elapsed:.1f}s, wrote {out_path}")

    return {
        "endpoint": PULID_ENDPOINT,
        "seed": result.get("seed"),
        "elapsed_seconds": round(elapsed, 1),
        "image_url": image_url,
        "persona_url": persona_url,
        "fal_pulid_params": fal_pulid_params,
    }


# ──────────────────────────────────────────────────────────────────────────
# Per-scenario orchestration
# ──────────────────────────────────────────────────────────────────────────

def process_scenario_full(
    scenario: dict,
    output_dir: Path,
    config: dict,
) -> dict:
    """Run the full from-scratch pipeline for one scenario. Never raises."""
    scenario_id = scenario.get("id", "?")
    output_dir.mkdir(parents=True, exist_ok=True)

    record: dict = {
        "scenario": scenario,
        "experiment": EXPERIMENT_NAME,
        "model_label": config.get("model_label", "FLUX (tuned, from scratch)"),
        "output_dir": str(output_dir),
        "is_full_run": True,
        "final_status": "pending",
    }

    # Save scenario yaml
    try:
        (output_dir / "01_scenario.yaml").write_text(
            yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8"
        )
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"failed writing 01_scenario.yaml: {e}"
        record["error_stage"] = "scenario_save"
        return record

    # ── 1. Step 1 prompt ──
    try:
        step_1_output = build_step_1_prompt(scenario)
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"Step 1 prompt build failed: {e}"
        record["error_stage"] = "step_1_prompt"
        return record

    step_1_text = (step_1_output or {}).get("step_1_image_prompt", "").strip()
    if not step_1_text:
        record["final_status"] = "failed"
        record["error_message"] = "step_1_image_prompt empty in Opus response"
        record["error_stage"] = "step_1_prompt"
        return record

    (output_dir / "02_step1_prompt.json").write_text(
        json.dumps(step_1_output, indent=2), encoding="utf-8"
    )
    record["step_1_output"] = step_1_output

    # ── 2. PuLID Stage 1 ──
    pulid_params = (
        config.get("step_1", {}).get("defaults", DEFAULT_PULID_PARAMS)
        or DEFAULT_PULID_PARAMS
    )
    persona_out_path = output_dir / "03_step1_persona.jpg"

    try:
        pulid_meta = run_pulid_step1(
            step_1_prompt_text=step_1_text,
            persona_local_path=str(PERSONA_JPG),
            fal_pulid_params=pulid_params,
            out_path=persona_out_path,
            scenario_id=scenario_id,
        )
        pulid_meta["cost_usd"] = COST_PULID_USD
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"PuLID Stage 1 failed: {e}"
        record["error_stage"] = "step_1_pulid"
        return record

    (output_dir / "03_step1_meta.json").write_text(
        json.dumps(pulid_meta, indent=2), encoding="utf-8"
    )
    record["step_1_pulid_meta"] = pulid_meta

    # ── 3. Step 2 prompt (FLUX-tuned) ──
    try:
        flux_step_2_output = prompt_builder_flux.build_step_2_prompt_flux(
            scenario, step_1_output
        )
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"Step 2 prompt build failed: {e}"
        record["error_stage"] = "step_2_prompt"
        return record

    flux_step_2_text = (flux_step_2_output or {}).get("step_2_image_prompt", "").strip()
    flux_negative = (flux_step_2_output or {}).get("negative_prompt", "").strip()
    if not flux_step_2_text:
        record["final_status"] = "failed"
        record["error_message"] = "step_2_image_prompt empty in Opus response"
        record["error_stage"] = "step_2_prompt"
        record["step_2_flux_prompt"] = flux_step_2_output
        return record

    (output_dir / "04_step2_flux_prompt.json").write_text(
        json.dumps(flux_step_2_output, indent=2), encoding="utf-8"
    )
    record["step_2_flux_prompt"] = flux_step_2_output

    # ── 4. FLUX Stage 2 ──
    flux_params = flux_step_2_output.get("fal_flux_params") or config.get(
        "step_2", {}
    ).get("defaults", {})
    flux_out_path = output_dir / "05_step2_flux.jpg"

    try:
        flux_meta = step_2_flux2_klein_edit.generate(
            persona_local_path=str(persona_out_path),
            product_local_path=str(PRODUCT_JPG),
            prompt=flux_step_2_text,
            negative_prompt=flux_negative,
            fal_flux_params=flux_params,
            out_path=flux_out_path,
            scenario_id=scenario_id,
        )
        flux_meta["cost_flux_api_usd"] = COST_FLUX_USD
        flux_meta["cost_pulid_api_usd"] = COST_PULID_USD
        flux_meta["cost_opus_step1_usd"] = COST_OPUS_STEP1_USD
        flux_meta["cost_opus_step2_usd"] = COST_OPUS_STEP2_USD
        flux_meta["cost_total_usd"] = COST_PER_SCENARIO_USD
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"FLUX Stage 2 failed: {e}"
        record["error_stage"] = "step_2_flux"
        return record

    (output_dir / "05_step2_flux_meta.json").write_text(
        json.dumps(flux_meta, indent=2), encoding="utf-8"
    )
    record["step_2_flux_meta"] = flux_meta
    record["final_status"] = "success"
    record["error_message"] = None

    # ── 5. Per-scenario chain.html (3-panel — no NB column in --full mode) ──
    try:
        batch_trace.write_chain_html(output_dir, record)
    except Exception as e:
        print(f"[scenario] {scenario_id}: chain.html write failed (non-fatal): {e}")

    return record


# ──────────────────────────────────────────────────────────────────────────
# Discovery, filtering, confirmation
# ──────────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_all_scenarios() -> list[dict]:
    if not SCENARIOS_YAML.exists():
        raise FileNotFoundError(f"missing scenarios file: {SCENARIOS_YAML}")
    data = yaml.safe_load(SCENARIOS_YAML.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        scenarios = data.get("scenarios", []) or data.get("items", []) or []
    elif isinstance(data, list):
        scenarios = data
    else:
        scenarios = []
    if not scenarios:
        raise RuntimeError(f"no scenarios found in {SCENARIOS_YAML}")
    return [s for s in scenarios if isinstance(s, dict) and s.get("id")]


def _verify_inputs() -> None:
    """Fail loudly BEFORE any API call if required files are missing."""
    problems = []

    if not PERSONA_JPG.exists():
        problems.append(f"missing persona reference: {PERSONA_JPG}")
    if not PRODUCT_JPG.exists():
        problems.append(f"missing product reference: {PRODUCT_JPG}")
    if not STEP_1_MASTER_PROMPT.exists():
        problems.append(f"missing Step 1 master prompt: {STEP_1_MASTER_PROMPT}")
    if not SCENARIOS_YAML.exists():
        problems.append(f"missing scenarios.yaml: {SCENARIOS_YAML}")

    flux_master = EXPERIMENT_DIR / "master_prompt_step2_flux.md"
    if not flux_master.exists():
        problems.append(f"missing FLUX-tuned master prompt: {flux_master}")

    if not os.getenv("FAL_KEY"):
        problems.append("FAL_KEY not set in environment (.env)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY not set in environment (.env)")

    if problems:
        msg = "[batch_full] pre-flight check failed — run halted before any API calls:\n  " + "\n  ".join(problems)
        raise RuntimeError(msg)


def _filter_scenarios(
    scenarios: list[dict],
    only: list[str] | None,
    exclude: list[str] | None,
) -> list[dict]:
    if only:
        only_set = set(only)
        scenarios = [s for s in scenarios if s.get("id") in only_set]
    if exclude:
        excl_set = set(exclude)
        scenarios = [s for s in scenarios if s.get("id") not in excl_set]
    return scenarios


def _confirm_cost(n: int, yes: bool) -> bool:
    total = COST_PER_SCENARIO_USD * n
    # FLUX 9b/base/edit (28 steps) ~15-25s, plus PuLID ~15-20s, plus 2x Opus
    # ~15s = ~50s per scenario.
    est_seconds = n * 50

    print("")
    print(f"[batch_full] scenarios:       {n}")
    print(f"[batch_full] per scenario:    ${COST_PER_SCENARIO_USD:.3f}")
    print(f"[batch_full]                    ${COST_PULID_USD:.3f}  PuLID Stage 1 (fal API)")
    print(f"[batch_full]                    ${COST_OPUS_STEP1_USD:.3f}  Step 1 prompt (Opus 4.7)")
    print(f"[batch_full]                    ${COST_OPUS_STEP2_USD:.3f}  Step 2 prompt (Opus 4.7)")
    print(f"[batch_full]                    ${COST_FLUX_USD:.3f}  FLUX-2 Klein 9B Base Edit (fal API)")
    print(f"[batch_full] estimated cost:  ${total:.2f}")
    print(f"[batch_full] est. wall time:  ~{est_seconds // 60} min ({est_seconds}s sequential)")

    if yes:
        print("[batch_full] --yes flag set, skipping confirmation")
        return True

    answer = input("[batch_full] proceed? (y/n): ").strip().lower()
    return answer in ("y", "yes")


# ──────────────────────────────────────────────────────────────────────────
# Manifest writer
# ──────────────────────────────────────────────────────────────────────────

def _write_manifest_and_overview(
    batch_dir: Path,
    records: list[dict],
    started_at: float,
    interrupted: bool,
    config: dict,
) -> None:
    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded

    actual_cost = 0.0
    for r in records:
        stage = r.get("error_stage")
        if r.get("final_status") == "success":
            actual_cost += COST_PER_SCENARIO_USD
        else:
            if stage == "scenario_save":
                actual_cost += 0.0
            elif stage == "step_1_prompt":
                actual_cost += COST_OPUS_STEP1_USD
            elif stage == "step_1_pulid":
                actual_cost += COST_OPUS_STEP1_USD + COST_PULID_USD
            elif stage == "step_2_prompt":
                actual_cost += COST_OPUS_STEP1_USD + COST_PULID_USD + COST_OPUS_STEP2_USD
            elif stage == "step_2_flux":
                actual_cost += (
                    COST_OPUS_STEP1_USD + COST_PULID_USD + COST_OPUS_STEP2_USD
                    + COST_FLUX_USD * 0.5
                )
            else:
                actual_cost += COST_OPUS_STEP1_USD

    summary = {
        "succeeded": succeeded,
        "failed": failed,
        "actual_cost_usd": round(actual_cost, 3),
        "elapsed_seconds": time.time() - started_at,
        "timestamp": batch_dir.name,
        "model_label": config.get("model_label", "FLUX (tuned, from scratch)"),
        "reuse_run_root": "(from scratch — no Plan A reuse)",
        "interrupted": interrupted,
        "is_full_run": True,
    }

    batch_trace.write_overview_html(batch_dir, records, summary)

    manifest = {
        **summary,
        "experiment": EXPERIMENT_NAME,
        "scenario_records": [
            {
                "scenario_id": r.get("scenario", {}).get("id", "?"),
                "final_status": r.get("final_status"),
                "error_stage": r.get("error_stage"),
                "error_message": r.get("error_message"),
                "step_1_word_count": r.get("step_1_output", {}).get("word_count"),
                "step_2_flux_word_count": r.get("step_2_flux_prompt", {}).get(
                    "word_count"
                ),
                "negative_prompt_present": bool(
                    (r.get("step_2_flux_prompt") or {}).get("negative_prompt", "").strip()
                ),
                "guidance_scale": (r.get("step_2_flux_prompt") or {})
                .get("fal_flux_params", {})
                .get("guidance_scale"),
                "step_1_seed": (r.get("step_1_pulid_meta") or {}).get("seed"),
                "step_2_flux_seed": (r.get("step_2_flux_meta") or {}).get("seed"),
                "step_1_elapsed_s": (r.get("step_1_pulid_meta") or {}).get(
                    "elapsed_seconds"
                ),
                "step_2_flux_elapsed_s": (r.get("step_2_flux_meta") or {}).get(
                    "elapsed_seconds"
                ),
            }
            for r in records
        ],
    }
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Full from-scratch batch runner for the flux_tuned_prompt experiment "
            "(no orientation picker, single product image). Generates "
            "Step 1 (PuLID) + Step 2 (FLUX-2 Klein 9B Base Edit, FLUX-tuned prompt) "
            "for every scenario in scenarios.yaml. No Plan A reuse."
        )
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="comma-separated scenario IDs to include (default: all)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        help="comma-separated scenario IDs to skip",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip cost confirmation prompt",
    )
    args = parser.parse_args()

    config = _load_config()

    try:
        _verify_inputs()
    except RuntimeError as e:
        print(str(e))
        return 1

    try:
        all_scenarios = _load_all_scenarios()
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[batch_full] {e}")
        return 1

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    exclude = [s.strip() for s in args.exclude.split(",")] if args.exclude else None
    scenarios = _filter_scenarios(all_scenarios, only, exclude)

    if not scenarios:
        print(f"[batch_full] no scenarios to run after filtering ({len(all_scenarios)} available)")
        if only:
            print(f"[batch_full]   --only filter: {only}")
        if exclude:
            print(f"[batch_full]   --exclude filter: {exclude}")
        return 1

    if not _confirm_cost(len(scenarios), args.yes):
        print("[batch_full] aborted by user")
        return 0

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    batch_dir = BATCH_OUTPUT_ROOT / f"{timestamp}_full"
    batch_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print(f"[batch_full] output dir:       {batch_dir}")
    print(f"[batch_full] scenarios queued: {len(scenarios)}")
    print("")

    records: list[dict] = []
    started_at = time.time()
    interrupted = False

    try:
        for i, scenario in enumerate(scenarios, start=1):
            sc_id = scenario.get("id", f"unknown_{i}")
            scenario_started = time.time()
            print(
                f"[batch_full] [{i}/{len(scenarios)}] {sc_id} — starting "
                f"({i-1} done, {len(scenarios)-i+1} remaining)"
            )

            output_dir = batch_dir / sc_id

            try:
                record = process_scenario_full(scenario, output_dir, config)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[batch_full]   {sc_id}: UNEXPECTED CRASH: {e}")
                record = {
                    "scenario": scenario,
                    "final_status": "failed",
                    "error_message": f"unhandled exception: {e}",
                    "error_stage": "unknown",
                    "experiment": EXPERIMENT_NAME,
                    "is_full_run": True,
                }

            records.append(record)

            elapsed = time.time() - scenario_started
            status = record.get("final_status", "?")
            stage_note = (
                f" (failed at: {record.get('error_stage', '?')})"
                if status != "success" else ""
            )
            print(
                f"[batch_full]   {sc_id}: {status.upper()} in {elapsed:.1f}s{stage_note}"
            )

            if i % 5 == 0:
                _write_manifest_and_overview(
                    batch_dir, records, started_at, interrupted=False,
                    config=config,
                )
                print(f"[batch_full]   (overview.html refreshed at {i}/{len(scenarios)})")

    except KeyboardInterrupt:
        interrupted = True
        print("")
        print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("[batch_full] interrupted by user (Ctrl+C)")
        print(f"[batch_full] writing partial overview for {len(records)} completed scenarios...")
        print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    _write_manifest_and_overview(
        batch_dir, records, started_at, interrupted=interrupted, config=config
    )

    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    elapsed_total = time.time() - started_at

    failure_stages: dict[str, int] = {}
    for r in records:
        if r.get("final_status") != "success":
            stage = r.get("error_stage", "unknown")
            failure_stages[stage] = failure_stages.get(stage, 0) + 1

    print("")
    print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[batch_full] DONE{'  (interrupted)' if interrupted else ''}")
    print(f"[batch_full]   succeeded:     {succeeded} / {len(records)}")
    print(f"[batch_full]   failed:        {failed}")
    print(f"[batch_full]   wall time:     {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")
    if failure_stages:
        print(f"[batch_full]   failures by stage:  " + ", ".join(
            f"{k}={v}" for k, v in sorted(failure_stages.items())
        ))
    print(f"[batch_full]   overview.html: {batch_dir / 'overview.html'}")
    print(f"[batch_full]   manifest.json: {batch_dir / 'batch_manifest.json'}")
    print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return 0 if (failed == 0 and not interrupted) else 2


if __name__ == "__main__":
    sys.exit(main())