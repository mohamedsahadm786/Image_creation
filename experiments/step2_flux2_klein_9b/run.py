"""
experiments/step2_flux2_klein_9b/run.py — single-scenario FLUX-2-Klein-9B Step 2 swap.

Re-runs Step 2 only, using fal-ai/flux-2/klein/9b/edit, against an existing
completed Plan A scenario's Step 1 output as fixed input — no new PuLID call,
no new Opus call.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_flux2_klein_9b.run \\
        --reuse-run outputs/runs/<timestamp>_plan_a/<scenario_id>

Optional:
    --rebuild-prompt    regenerate the Step 2 prompt via Opus 4.7 (default: reuse baseline prompt)

For a batch run over an entire Plan A run dir, see batch_runner/run_batch.py.

Output goes to:
    experiments/step2_flux2_klein_9b/outputs/<timestamp>_<scenario_id>/
"""

import argparse
import json
import shutil
import sys
import yaml
from datetime import datetime
from pathlib import Path

# Allow importing src.* modules from the project root when run as -m experiments.*
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.step2_flux2_klein_9b import step_2_flux2_klein
from experiments.step2_flux2_klein_9b import trace_html as exp_trace


EXPERIMENT_NAME = "step2_flux2_klein_9b"
EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
OUTPUT_ROOT = EXPERIMENT_DIR / "outputs"

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
    rebuild_prompt: bool = False,
) -> dict:
    """
    Run FLUX-2-Klein-9B Step 2 against one Plan A scenario directory.
    Returns a record dict (always — never raises).
    """
    scenario_id = reuse_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    missing = [f for f in REQUIRED_FILES if not (reuse_dir / f).exists()]
    if missing:
        return {
            "scenario": {"id": scenario_id},
            "final_status": "failed",
            "error_message": f"reuse-run dir missing required files: {missing}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "FLUX-2-Klein-9B"),
        }

    scenario = _load_yaml(reuse_dir / "01_scenario.yaml")
    step_1_output = _load_json(reuse_dir / "02_step1_prompt.json")

    if rebuild_prompt:
        print(f"[{scenario_id}] regenerating Step 2 prompt via Opus 4.7")
        from src.prompt_builder import build_step_2_prompt
        step_2_output = build_step_2_prompt(scenario, step_1_output)
    else:
        step_2_output = _load_json(reuse_dir / "04_step2_prompt.json")

    step_2_prompt_text = step_2_output.get("step_2_image_prompt", "").strip()
    if not step_2_prompt_text:
        return {
            "scenario": scenario,
            "final_status": "failed",
            "error_message": "step_2_image_prompt is empty in the prompt JSON",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "FLUX-2-Klein-9B"),
        }

    flux2_params = config.get("step_2", {}).get("defaults", {})
    cost_per_image = config.get("step_2", {}).get("cost_per_image_usd", 0.025)
    model_label = config.get("model_label", "FLUX-2-Klein-9B")

    # Copy reference files for self-containment
    shutil.copy(reuse_dir / "01_scenario.yaml", output_dir / "01_scenario.yaml")
    shutil.copy(reuse_dir / "02_step1_prompt.json", output_dir / "02_step1_prompt.json")
    shutil.copy(reuse_dir / "03_step1_persona.jpg", output_dir / "03_step1_persona.jpg")
    (output_dir / "04_step2_prompt.json").write_text(
        json.dumps(step_2_output, indent=2), encoding="utf-8"
    )

    nano_banana_meta = None
    nb_image_path = reuse_dir / "05_step2_final.jpg"
    nb_meta_path = reuse_dir / "05_step2_meta.json"
    if nb_image_path.exists():
        shutil.copy(nb_image_path, output_dir / "05_step2_nano_banana.jpg")
    if nb_meta_path.exists():
        shutil.copy(nb_meta_path, output_dir / "05_step2_nano_banana_meta.json")
        try:
            nano_banana_meta = _load_json(nb_meta_path)
        except Exception:
            nano_banana_meta = None

    # Run FLUX-2-Klein-9B Step 2
    flux2_out_path = output_dir / "05_step2_flux2_klein_final.jpg"
    flux2_meta: dict = {}
    final_status = "success"
    error_message = None

    try:
        flux2_meta = step_2_flux2_klein.generate(
            step_1_local_path=str(output_dir / "03_step1_persona.jpg"),
            step_2_prompt=step_2_prompt_text,
            fal_flux2_params=flux2_params,
            out_path=flux2_out_path,
            scenario_id=scenario_id,
        )
        flux2_meta["cost_usd"] = cost_per_image
    except Exception as e:
        final_status = "failed"
        error_message = str(e)
        flux2_meta = {"error": error_message, "endpoint": "fal-ai/flux-2/klein/9b/edit"}
        print(f"[{scenario_id}] FAILED: {e}")

    (output_dir / "05_step2_flux2_klein_meta.json").write_text(
        json.dumps(flux2_meta, indent=2), encoding="utf-8"
    )

    record = {
        "scenario": scenario,
        "step_1_output": step_1_output,
        "step_2_output": step_2_output,
        "step_2_flux2_meta": flux2_meta,
        "step_2_nano_banana_meta": nano_banana_meta,
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
        description="Re-run Step 2 with FLUX-2-Klein-9B against a single Plan A scenario."
    )
    parser.add_argument(
        "--reuse-run",
        type=Path,
        required=True,
        help="path to a completed Plan A scenario directory",
    )
    parser.add_argument(
        "--rebuild-prompt",
        action="store_true",
        help="regenerate the Step 2 prompt via Opus 4.7 instead of reusing the baseline",
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

    print(f"[run] output dir: {output_dir}")
    record = process_scenario(reuse_dir, output_dir, config, args.rebuild_prompt)

    final_status = record.get("final_status")
    flux2_meta = record.get("step_2_flux2_meta") or {}

    print("")
    print(f"[run] {str(final_status).upper()}")
    print(f"[run]   scenario:   {scenario_id}")
    print(f"[run]   chain.html: {output_dir / 'chain.html'}")
    if final_status == "success":
        print(f"[run]   elapsed:    {flux2_meta.get('elapsed_seconds', 0):.1f}s")
        print(f"[run]   cost:       ${flux2_meta.get('cost_usd', 0):.3f}")
    else:
        print(f"[run]   error:      {record.get('error_message')}")

    return 0 if final_status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())