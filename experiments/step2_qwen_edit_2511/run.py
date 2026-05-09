"""
experiments/step2_qwen_edit_2511/run.py — Step 2 model swap experiment.

Re-runs Step 2 only, swapping fal-ai/nano-banana-2/edit for
fal-ai/qwen-image-edit-2511. Uses an existing completed Plan A scenario's
Step 1 output as fixed input — no new PuLID call, no new Opus call.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_qwen_edit_2511.run \\
        --reuse-run outputs/runs/<timestamp>_plan_a/<scenario_id>

Optional flags:
    --rebuild-prompt    regenerate Step 2 prompt via Opus 4.7 instead of
                        reusing the existing 04_step2_prompt.json.
                        Default: reuse (true apples-to-apples comparison).

Output goes to:
    experiments/step2_qwen_edit_2511/outputs/<timestamp>_<scenario_id>/

Files produced in that directory:
    01_scenario.yaml            (copied from baseline run)
    02_step1_prompt.json        (copied)
    03_step1_persona.jpg        (copied)
    04_step2_prompt.json        (copied — same prompt for both models)
    05_step2_nano_banana.jpg    (copied — baseline output for comparison)
    05_step2_nano_banana_meta.json (copied if available)
    05_step2_qwen_final.jpg     (NEW — the Qwen output)
    05_step2_qwen_meta.json     (NEW — timing, seed, request_id)
    chain.html                  (4-panel side-by-side view)
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

from experiments.step2_qwen_edit_2511 import step_2_qwen_edit
from experiments.step2_qwen_edit_2511 import trace_html as exp_trace


EXPERIMENT_NAME = "step2_qwen_edit_2511"
EXPERIMENT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
OUTPUT_ROOT = EXPERIMENT_DIR / "outputs"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-run Step 2 with Qwen-Image-Edit-2511 against an existing Plan A scenario."
    )
    parser.add_argument(
        "--reuse-run",
        type=Path,
        required=True,
        help="path to a completed Plan A scenario directory, e.g. "
             "outputs/runs/20251108_120000_plan_a/outdoor_golden_hour_patio_27",
    )
    parser.add_argument(
        "--rebuild-prompt",
        action="store_true",
        help="regenerate the Step 2 prompt via Opus 4.7 instead of reusing the baseline prompt",
    )
    args = parser.parse_args()

    reuse_dir: Path = args.reuse_run
    if not reuse_dir.exists() or not reuse_dir.is_dir():
        print(f"[run] reuse-run path does not exist or is not a directory: {reuse_dir}")
        return 1

    # ---------- Required input files in the reuse-run dir ----------
    required = {
        "scenario": reuse_dir / "01_scenario.yaml",
        "step_1_prompt": reuse_dir / "02_step1_prompt.json",
        "step_1_image": reuse_dir / "03_step1_persona.jpg",
        "step_2_prompt": reuse_dir / "04_step2_prompt.json",
    }
    optional = {
        "step_2_nano_banana_image": reuse_dir / "05_step2_final.jpg",
        "step_2_nano_banana_meta": reuse_dir / "05_step2_meta.json",
    }

    missing = [k for k, p in required.items() if not p.exists()]
    if missing:
        print(f"[run] reuse-run dir is missing required files: {missing}")
        print(f"[run]   path: {reuse_dir}")
        return 1

    # ---------- Load context ----------
    scenario = _load_yaml(required["scenario"])
    step_1_output = _load_json(required["step_1_prompt"])
    scenario_id = scenario.get("id", "unknown")

    # ---------- Step 2 prompt: reuse or rebuild ----------
    if args.rebuild_prompt:
        print("[run] regenerating Step 2 prompt via Opus 4.7 (--rebuild-prompt)")
        from src.prompt_builder import build_step_2_prompt
        step_2_output = build_step_2_prompt(scenario, step_1_output)
    else:
        print("[run] reusing existing Step 2 prompt (true apples-to-apples comparison)")
        step_2_output = _load_json(required["step_2_prompt"])

    step_2_prompt_text = step_2_output.get("step_2_image_prompt", "").strip()
    if not step_2_prompt_text:
        print("[run] FATAL: step_2_image_prompt is empty in the prompt JSON")
        return 1

    # ---------- Config ----------
    config = _load_config()
    qwen_params = config.get("step_2", {}).get("defaults", {})
    cost_per_image = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    model_label = config.get("model_label", "Qwen-Image-Edit-2511")

    # ---------- Output directory ----------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / f"{timestamp}_{scenario_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[run] output dir: {out_dir}")

    # ---------- Copy reference files for self-containment ----------
    shutil.copy(required["scenario"], out_dir / "01_scenario.yaml")
    shutil.copy(required["step_1_prompt"], out_dir / "02_step1_prompt.json")
    shutil.copy(required["step_1_image"], out_dir / "03_step1_persona.jpg")
    (out_dir / "04_step2_prompt.json").write_text(
        json.dumps(step_2_output, indent=2), encoding="utf-8"
    )

    nano_banana_meta = None
    if optional["step_2_nano_banana_image"].exists():
        shutil.copy(
            optional["step_2_nano_banana_image"],
            out_dir / "05_step2_nano_banana.jpg",
        )
    else:
        print("[run]   note: baseline 05_step2_final.jpg not found in reuse-run dir")

    if optional["step_2_nano_banana_meta"].exists():
        shutil.copy(
            optional["step_2_nano_banana_meta"],
            out_dir / "05_step2_nano_banana_meta.json",
        )
        try:
            nano_banana_meta = _load_json(optional["step_2_nano_banana_meta"])
        except Exception:
            nano_banana_meta = None

    # ---------- Run Qwen Step 2 ----------
    qwen_out_path = out_dir / "05_step2_qwen_final.jpg"
    qwen_meta: dict = {}
    final_status = "success"
    error_message = None

    try:
        qwen_meta = step_2_qwen_edit.generate(
            step_1_local_path=str(out_dir / "03_step1_persona.jpg"),
            step_2_prompt=step_2_prompt_text,
            fal_qwen_params=qwen_params,
            out_path=qwen_out_path,
            scenario_id=scenario_id,
        )
        # Override cost_usd with the value from config (single source of truth)
        qwen_meta["cost_usd"] = cost_per_image
    except Exception as e:
        final_status = "failed"
        error_message = str(e)
        qwen_meta = {"error": error_message, "endpoint": "fal-ai/qwen-image-edit-2511"}
        print(f"[run] FAILED: {e}")

    (out_dir / "05_step2_qwen_meta.json").write_text(
        json.dumps(qwen_meta, indent=2), encoding="utf-8"
    )

    # ---------- Build chain.html ----------
    record = {
        "scenario": scenario,
        "step_1_output": step_1_output,
        "step_2_output": step_2_output,
        "step_2_qwen_meta": qwen_meta,
        "step_2_nano_banana_meta": nano_banana_meta,
        "final_status": final_status,
        "error_message": error_message,
        "experiment": EXPERIMENT_NAME,
        "model_label": model_label,
        "reused_run_path": str(reuse_dir),
    }
    exp_trace.write_chain_html(out_dir, record)

    # ---------- Summary ----------
    print("")
    print(f"[run] {final_status.upper()}")
    print(f"[run]   scenario:   {scenario_id}")
    print(f"[run]   chain.html: {out_dir / 'chain.html'}")
    if final_status == "success":
        print(f"[run]   elapsed:    {qwen_meta.get('elapsed_seconds', 0):.1f}s")
        print(f"[run]   cost:       ${qwen_meta.get('cost_usd', 0):.3f}")

    return 0 if final_status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())