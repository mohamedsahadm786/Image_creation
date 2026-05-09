"""
experiments/step2_qwen_edit_2511/qwen_tuned_prompt/run.py — single-scenario
re-run with the NEW Qwen-tuned Step 2 prompt.

Pipeline for one scenario:
  1. Read scenario.yaml, step_1_prompt.json from the baseline Plan A scenario dir
  2. Call Opus 4.7 with master_prompt_step2_qwen.md → NEW Step 2 prompt
  3. Save the NEW prompt as 04_step2_qwen_prompt.json (and copy the OLD
     NB-shaped prompt as 04_step2_nb_prompt.json for diff inspection)
  4. Copy the Step 1 PuLID image (03_step1_persona.jpg) — input to Qwen
  5. Copy the NB baseline output → 05_step2_nb.jpg
  6. Copy the OLD Qwen-with-NB-prompt output (if --reuse-qwen-v1 provided)
     → 05_step2_qwen_v1.jpg
  7. Call Qwen with the NEW prompt → 05_step2_qwen_v2.jpg (NEW)
  8. Generate chain.html with 5 panels:
       Step 0 persona → Step 1 PuLID → Step 2a NB → Step 2b Qwen-v1 → Step 2c Qwen-v2

For batch operation see batch_runner/run_batch.py.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.run \\
        --reuse-run outputs/runs/2026-05-08_17-04-15_plan_a/pilates_mat_morning_handheld_09 \\
        --reuse-qwen-v1 experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch/pilates_mat_morning_handheld_09

The --reuse-qwen-v1 path is OPTIONAL. If provided and the directory exists,
the chain.html will show the v1 panel; if omitted, the v1 panel renders empty
with a "not provided" placeholder.
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

# Reuse the existing Qwen API caller from the parent experiment (UNCHANGED)
from experiments.step2_qwen_edit_2511 import step_2_qwen_edit
# This experiment's own modules
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt import prompt_builder_qwen
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt import trace_html as exp_trace


EXPERIMENT_NAME = "step2_qwen_edit_2511_with_qwen_tuned_prompt"
EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
OUTPUT_ROOT = EXPERIMENT_DIR / "outputs"

# Required files in the baseline Plan A scenario dir
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
    qwen_v1_dir: Path | None = None,
) -> dict:
    """
    Run the qwen_tuned_prompt pipeline against one Plan A scenario directory.
    Returns a record dict — never raises.
    """
    scenario_id = reuse_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 1. Validate baseline ----------
    missing = [f for f in REQUIRED_FILES if not (reuse_dir / f).exists()]
    if missing:
        return {
            "scenario": {"id": scenario_id},
            "final_status": "failed",
            "error_message": f"baseline reuse-run dir missing required files: {missing}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen (qwen-tuned prompt)"),
        }

    scenario = _load_yaml(reuse_dir / "01_scenario.yaml")
    step_1_output = _load_json(reuse_dir / "02_step1_prompt.json")
    nb_step_2_output = _load_json(reuse_dir / "04_step2_prompt.json")  # OLD NB-shaped prompt

    # ---------- 2. Generate NEW Qwen-tuned Step 2 prompt via Opus ----------
    try:
        qwen_step_2_output = prompt_builder_qwen.build_step_2_prompt_qwen(
            scenario, step_1_output
        )
    except Exception as e:
        return {
            "scenario": scenario,
            "final_status": "failed",
            "error_message": f"Opus prompt regeneration failed: {e}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen (qwen-tuned prompt)"),
        }

    qwen_step_2_prompt_text = qwen_step_2_output.get("step_2_image_prompt", "").strip()
    if not qwen_step_2_prompt_text:
        return {
            "scenario": scenario,
            "final_status": "failed",
            "error_message": "Qwen-tuned step_2_image_prompt is empty in the prompt JSON",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen (qwen-tuned prompt)"),
        }

    # ---------- 3. Save / copy reference files ----------
    shutil.copy(reuse_dir / "01_scenario.yaml", output_dir / "01_scenario.yaml")
    shutil.copy(reuse_dir / "02_step1_prompt.json", output_dir / "02_step1_prompt.json")
    shutil.copy(reuse_dir / "03_step1_persona.jpg", output_dir / "03_step1_persona.jpg")

    # OLD NB-shaped prompt (copied for diff inspection)
    (output_dir / "04_step2_nb_prompt.json").write_text(
        json.dumps(nb_step_2_output, indent=2), encoding="utf-8"
    )
    # NEW Qwen-tuned prompt
    (output_dir / "04_step2_qwen_prompt.json").write_text(
        json.dumps(qwen_step_2_output, indent=2), encoding="utf-8"
    )

    # ---------- 4. Copy NB baseline image ----------
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

    # ---------- 5. Copy Qwen-v1 image (if provided) ----------
    qwen_v1_meta = None
    if qwen_v1_dir is not None and qwen_v1_dir.exists() and qwen_v1_dir.is_dir():
        v1_image_path = qwen_v1_dir / "05_step2_qwen_final.jpg"
        v1_meta_path = qwen_v1_dir / "05_step2_qwen_meta.json"
        if v1_image_path.exists():
            shutil.copy(v1_image_path, output_dir / "05_step2_qwen_v1.jpg")
        if v1_meta_path.exists():
            shutil.copy(v1_meta_path, output_dir / "05_step2_qwen_v1_meta.json")
            try:
                qwen_v1_meta = _load_json(v1_meta_path)
            except Exception:
                qwen_v1_meta = None

    # ---------- 6. Run Qwen with NEW prompt ----------
    qwen_params = config.get("step_2", {}).get("defaults", {})
    cost_qwen = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    cost_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.18)
    model_label = config.get("model_label", "Qwen (qwen-tuned prompt)")

    qwen_v2_out_path = output_dir / "05_step2_qwen_v2.jpg"
    qwen_v2_meta: dict = {}
    final_status = "success"
    error_message = None

    try:
        qwen_v2_meta = step_2_qwen_edit.generate(
            step_1_local_path=str(output_dir / "03_step1_persona.jpg"),
            step_2_prompt=qwen_step_2_prompt_text,
            fal_qwen_params=qwen_params,
            out_path=qwen_v2_out_path,
            scenario_id=scenario_id,
        )
        qwen_v2_meta["cost_qwen_api_usd"] = cost_qwen
        qwen_v2_meta["cost_opus_prompt_usd"] = cost_opus
        qwen_v2_meta["cost_total_usd"] = cost_qwen + cost_opus
    except Exception as e:
        final_status = "failed"
        error_message = str(e)
        qwen_v2_meta = {"error": error_message, "endpoint": "fal-ai/qwen-image-edit-2511"}
        print(f"[{scenario_id}] Qwen v2 FAILED: {e}")

    (output_dir / "05_step2_qwen_v2_meta.json").write_text(
        json.dumps(qwen_v2_meta, indent=2), encoding="utf-8"
    )

    # ---------- 7. Build chain.html (5 panels) ----------
    record = {
        "scenario": scenario,
        "step_1_output": step_1_output,
        "step_2_nb_prompt": nb_step_2_output,         # OLD prompt
        "step_2_qwen_prompt": qwen_step_2_output,      # NEW prompt
        "step_2_nb_meta": nano_banana_meta,
        "step_2_qwen_v1_meta": qwen_v1_meta,
        "step_2_qwen_v2_meta": qwen_v2_meta,
        "final_status": final_status,
        "error_message": error_message,
        "experiment": EXPERIMENT_NAME,
        "model_label": model_label,
        "reused_run_path": str(reuse_dir),
        "qwen_v1_reused_path": str(qwen_v1_dir) if qwen_v1_dir else None,
        "output_dir": str(output_dir),
    }
    exp_trace.write_chain_html(output_dir, record)

    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-run Step 2 with Qwen using the new Qwen-tuned prompt for one scenario."
    )
    parser.add_argument(
        "--reuse-run",
        type=Path,
        required=True,
        help="path to a completed Plan A scenario directory "
             "(provides scenario, step 1, NB baseline)",
    )
    parser.add_argument(
        "--reuse-qwen-v1",
        type=Path,
        default=None,
        help="OPTIONAL — path to the matching scenario subdir from a previous "
             "step2_qwen_edit_2511 batch (provides the v1 Qwen image with the "
             "OLD NB-shaped prompt for the A/B/C comparison)",
    )
    args = parser.parse_args()

    reuse_dir: Path = args.reuse_run
    if not reuse_dir.exists() or not reuse_dir.is_dir():
        print(f"[run] reuse-run path does not exist or is not a directory: {reuse_dir}")
        return 1

    qwen_v1_dir: Path | None = args.reuse_qwen_v1
    if qwen_v1_dir is not None and (not qwen_v1_dir.exists() or not qwen_v1_dir.is_dir()):
        print(f"[run] WARNING: --reuse-qwen-v1 path not found, will skip v1 panel: {qwen_v1_dir}")
        qwen_v1_dir = None

    config = load_config()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    scenario_id = reuse_dir.name
    output_dir = OUTPUT_ROOT / f"{timestamp}_{scenario_id}"

    print(f"[run] output dir:    {output_dir}")
    print(f"[run] reuse-run:     {reuse_dir}")
    print(f"[run] reuse-qwen-v1: {qwen_v1_dir if qwen_v1_dir else '(none — v1 panel will be empty)'}")

    record = process_scenario(reuse_dir, output_dir, config, qwen_v1_dir)

    final_status = record.get("final_status")
    qwen_v2_meta = record.get("step_2_qwen_v2_meta") or {}

    print("")
    print(f"[run] {str(final_status).upper()}")
    print(f"[run]   scenario:   {scenario_id}")
    print(f"[run]   chain.html: {output_dir / 'chain.html'}")
    if final_status == "success":
        print(f"[run]   qwen call:  {qwen_v2_meta.get('elapsed_seconds', 0):.1f}s")
        print(f"[run]   total cost: ${qwen_v2_meta.get('cost_total_usd', 0):.3f} "
              f"(qwen ${qwen_v2_meta.get('cost_qwen_api_usd', 0):.3f} + "
              f"opus ${qwen_v2_meta.get('cost_opus_prompt_usd', 0):.3f})")
    else:
        print(f"[run]   error:      {record.get('error_message')}")

    return 0 if final_status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())