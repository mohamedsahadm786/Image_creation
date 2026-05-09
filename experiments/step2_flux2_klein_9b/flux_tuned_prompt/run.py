"""
experiments/step2_flux2_klein_9b/flux_tuned_prompt/run.py

Single-scenario re-run with the FLUX-tuned prompt pipeline (reuse mode).
Runs against an existing Plan A baseline scenario directory.

Pipeline per scenario:
  1. Read scenario.yaml + step_1_prompt.json from baseline Plan A scenario dir
  2. Call Opus 4.7 with master_prompt_step2_flux.md → FLUX-tuned Step 2 prompt
     (with negative_prompt + fal_flux_params)
  3. Call FLUX-2 Klein 9B Base Edit with persona + assets/product.jpg
  4. Copy NB baseline for A/B comparison
  5. Generate chain.html (4 panels + prompt diff)

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.run --reuse-run outputs/runs/2026-05-08_17-04-15_plan_a/bedroom_robe_with_product_13
"""

import argparse
import json
import shutil
import sys
import yaml
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# This experiment's own modules
from experiments.step2_flux2_klein_9b.flux_tuned_prompt import prompt_builder_flux
from experiments.step2_flux2_klein_9b.flux_tuned_prompt import step_2_flux2_klein_edit
from experiments.step2_flux2_klein_9b.flux_tuned_prompt import trace_html as exp_trace


EXPERIMENT_NAME = "step2_flux2_klein_9b_with_flux_tuned_prompt"
EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
OUTPUT_ROOT = EXPERIMENT_DIR / "outputs"
PRODUCT_JPG = PROJECT_ROOT / "assets" / "product.jpg"

REQUIRED_FILES = (
    "01_scenario.yaml",
    "02_step1_prompt.json",
    "03_step1_persona.jpg",
    "04_step2_prompt.json",
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def process_scenario(
    reuse_dir: Path,
    output_dir: Path,
    config: dict,
) -> dict:
    """Run the FLUX-tuned-prompt pipeline against one Plan A scenario.
    Returns a record dict — never raises."""
    scenario_id = reuse_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Validate baseline ---
    missing = [f for f in REQUIRED_FILES if not (reuse_dir / f).exists()]
    if missing:
        return {
            "scenario": {"id": scenario_id},
            "final_status": "failed",
            "error_message": f"baseline reuse-run dir missing required files: {missing}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "FLUX (tuned)"),
        }

    if not PRODUCT_JPG.exists():
        return {
            "scenario": {"id": scenario_id},
            "final_status": "failed",
            "error_message": f"missing product reference: {PRODUCT_JPG}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "FLUX (tuned)"),
        }

    scenario = _load_yaml(reuse_dir / "01_scenario.yaml")
    step_1_output = _load_json(reuse_dir / "02_step1_prompt.json")
    nb_step_2_output = _load_json(reuse_dir / "04_step2_prompt.json")

    # --- 2. Generate FLUX-tuned Step 2 prompt via Opus ---
    try:
        flux_step_2_output = prompt_builder_flux.build_step_2_prompt_flux(
            scenario, step_1_output
        )
    except Exception as e:
        return {
            "scenario": scenario,
            "final_status": "failed",
            "error_message": f"Opus prompt regeneration failed: {e}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "FLUX (tuned)"),
        }

    flux_step_2_prompt_text = flux_step_2_output.get("step_2_image_prompt", "").strip()
    flux_negative_prompt = flux_step_2_output.get("negative_prompt", "").strip()
    if not flux_step_2_prompt_text:
        return {
            "scenario": scenario,
            "final_status": "failed",
            "error_message": "FLUX-tuned step_2_image_prompt is empty in the prompt JSON",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "FLUX (tuned)"),
        }

    # --- 3. Save / copy reference files ---
    shutil.copy(reuse_dir / "01_scenario.yaml", output_dir / "01_scenario.yaml")
    shutil.copy(reuse_dir / "02_step1_prompt.json", output_dir / "02_step1_prompt.json")
    shutil.copy(reuse_dir / "03_step1_persona.jpg", output_dir / "03_step1_persona.jpg")

    (output_dir / "04_step2_nb_prompt.json").write_text(
        json.dumps(nb_step_2_output, indent=2), encoding="utf-8"
    )
    (output_dir / "04_step2_flux_prompt.json").write_text(
        json.dumps(flux_step_2_output, indent=2), encoding="utf-8"
    )

    # --- 4. Copy NB baseline image ---
    nb_image_path = reuse_dir / "05_step2_final.jpg"
    nb_meta_path = reuse_dir / "05_step2_meta.json"
    nano_banana_meta = None
    if nb_image_path.exists():
        shutil.copy(nb_image_path, output_dir / "05_step2_nb.jpg")
    if nb_meta_path.exists():
        shutil.copy(nb_meta_path, output_dir / "05_step2_nb_meta.json")
        try:
            nano_banana_meta = _load_json(nb_meta_path)
        except Exception:
            nano_banana_meta = None

    # --- 5. Run FLUX with FLUX-tuned prompt ---
    # Prefer fal_flux_params from the prompt envelope (per-scenario tuning),
    # fall back to config defaults.
    flux_params = flux_step_2_output.get("fal_flux_params") or config.get(
        "step_2", {}
    ).get("defaults", {})

    cost_flux = config.get("step_2", {}).get("cost_per_image_usd", 0.05)
    cost_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.15)
    model_label = config.get("model_label", "FLUX (tuned)")

    flux_out_path = output_dir / "05_step2_flux.jpg"
    flux_meta: dict = {}
    final_status = "success"
    error_message = None

    try:
        flux_meta = step_2_flux2_klein_edit.generate(
            persona_local_path=str(output_dir / "03_step1_persona.jpg"),
            product_local_path=str(PRODUCT_JPG),
            prompt=flux_step_2_prompt_text,
            negative_prompt=flux_negative_prompt,
            fal_flux_params=flux_params,
            out_path=flux_out_path,
            scenario_id=scenario_id,
        )
        flux_meta["cost_flux_api_usd"] = cost_flux
        flux_meta["cost_opus_prompt_usd"] = cost_opus
        flux_meta["cost_total_usd"] = cost_flux + cost_opus
    except Exception as e:
        final_status = "failed"
        error_message = str(e)
        flux_meta = {
            "error": error_message,
            "endpoint": "fal-ai/flux-2/klein/9b/base/edit",
        }
        print(f"[{scenario_id}] FLUX FAILED: {e}")

    (output_dir / "05_step2_flux_meta.json").write_text(
        json.dumps(flux_meta, indent=2), encoding="utf-8"
    )

    # --- 6. Build chain.html (4 panels: Step 0 / Step 1 / NB / FLUX) ---
    record = {
        "scenario": scenario,
        "step_1_output": step_1_output,
        "step_2_nb_prompt": nb_step_2_output,
        "step_2_flux_prompt": flux_step_2_output,
        "step_2_nb_meta": nano_banana_meta,
        "step_2_flux_meta": flux_meta,
        "final_status": final_status,
        "error_message": error_message,
        "experiment": EXPERIMENT_NAME,
        "model_label": model_label,
        "reused_run_path": str(reuse_dir),
        "output_dir": str(output_dir),
    }
    exp_trace.write_chain_html(output_dir, record)

    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-run Step 2 with FLUX-tuned prompt for one scenario."
    )
    parser.add_argument(
        "--reuse-run",
        type=Path,
        required=True,
        help="path to a completed Plan A scenario directory",
    )
    args = parser.parse_args()

    reuse_dir: Path = args.reuse_run
    if not reuse_dir.exists() or not reuse_dir.is_dir():
        print(f"[run] reuse-run path does not exist or is not a directory: {reuse_dir}")
        return 1

    config = load_config()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    scenario_id = reuse_dir.name
    output_dir = OUTPUT_ROOT / f"{timestamp}_{scenario_id}"

    print(f"[run] output dir:    {output_dir}")
    print(f"[run] reuse-run:     {reuse_dir}")

    record = process_scenario(reuse_dir, output_dir, config)

    final_status = record.get("final_status")
    flux_meta = record.get("step_2_flux_meta") or {}
    flux_prompt = record.get("step_2_flux_prompt") or {}

    print("")
    print(f"[run] {str(final_status).upper()}")
    print(f"[run]   scenario:    {scenario_id}")
    print(f"[run]   word count:  {flux_prompt.get('word_count', '—')}")
    print(f"[run]   chain.html:  {output_dir / 'chain.html'}")
    if final_status == "success":
        print(f"[run]   flux call:   {flux_meta.get('elapsed_seconds', 0):.1f}s")
        print(
            f"[run]   total cost:  ${flux_meta.get('cost_total_usd', 0):.3f} "
            f"(flux ${flux_meta.get('cost_flux_api_usd', 0):.3f} + "
            f"opus ${flux_meta.get('cost_opus_prompt_usd', 0):.3f})"
        )
    else:
        print(f"[run]   error:       {record.get('error_message')}")

    return 0 if final_status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())