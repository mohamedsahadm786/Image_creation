"""
run_batch.py — batch Qwen Step 2 swap.

Self-contained. Does NOT depend on or modify run.py or trace_html.py at the
parent experiment level. Imports only the unchanged step_2_qwen_edit.py for
the fal API call, and reads config.yaml from the parent folder so single-run
and batch use identical Qwen parameters.

Re-runs Step 2 with Qwen-Image-Edit-2511 across ALL scenarios from an existing
Plan A run, sequentially.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch \\
        --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a

Optional:
    --only id1 id2 ...        only run these scenario IDs
    --exclude id1 id2 ...     skip these scenario IDs
    --yes                     skip the cost-confirmation prompt
    --rebuild-prompt          regenerate Step 2 prompts via Opus (default: reuse baseline)

Output goes to:
    experiments/step2_qwen_edit_2511/batch_runner/outputs/<timestamp>_batch/
        overview.html              (A/B grid of all scenarios — open this first)
        batch_summary.json         (totals: succeeded/failed/cost/elapsed)
        all_records.json           (per-scenario lightweight records)
        <scenario_id>/             (one subdir per scenario)
            01_scenario.yaml
            02_step1_prompt.json
            03_step1_persona.jpg
            04_step2_prompt.json
            05_step2_nano_banana.jpg          (baseline — copied)
            05_step2_nano_banana_meta.json    (baseline meta — copied)
            05_step2_qwen_final.jpg           (NEW)
            05_step2_qwen_meta.json           (NEW)
            chain.html                        (4-panel A/B drill-down)
"""

import argparse
import json
import shutil
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

# Project root is 4 levels up from this file:
#   batch_runner/run_batch.py
#     ↑ batch_runner
#       ↑ step2_qwen_edit_2511
#         ↑ experiments
#           ↑ project_root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the API caller (unchanged) from the parent experiment folder
from experiments.step2_qwen_edit_2511 import step_2_qwen_edit
# Import this folder's HTML generators
from experiments.step2_qwen_edit_2511.batch_runner import trace_html_batch as batch_trace


EXPERIMENT_NAME = "step2_qwen_edit_2511"

# Path constants relative to this file
BATCH_RUNNER_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = BATCH_RUNNER_DIR.parent
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"        # shared with single-run
OUTPUT_ROOT = BATCH_RUNNER_DIR / "outputs"           # batch-only outputs

REQUIRED_FILES = (
    "01_scenario.yaml",
    "02_step1_prompt.json",
    "03_step1_persona.jpg",
    "04_step2_prompt.json",
)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_scenario_dirs(root: Path) -> list[Path]:
    """Find scenario subdirs under root that have all required Plan A files."""
    if not root.exists() or not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if any(not (child / f).exists() for f in REQUIRED_FILES):
            continue
        out.append(child)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Per-scenario processor (self-contained inside batch_runner)
# ──────────────────────────────────────────────────────────────────────────

def _process_scenario(
    reuse_dir: Path,
    output_dir: Path,
    config: dict,
    rebuild_prompt: bool = False,
) -> dict:
    """
    Run Qwen Step 2 against one Plan A scenario directory.
    Returns a record dict — never raises (caller stays in control of the loop).
    """
    scenario_id = reuse_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Validate ----------
    missing = [f for f in REQUIRED_FILES if not (reuse_dir / f).exists()]
    if missing:
        return {
            "scenario": {"id": scenario_id},
            "final_status": "failed",
            "error_message": f"reuse-run dir missing required files: {missing}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen-Image-Edit-2511"),
            "output_dir": str(output_dir),
        }

    # ---------- Load context ----------
    scenario = _load_yaml(reuse_dir / "01_scenario.yaml")
    step_1_output = _load_json(reuse_dir / "02_step1_prompt.json")

    # ---------- Step 2 prompt: reuse or rebuild ----------
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
            "model_label": config.get("model_label", "Qwen-Image-Edit-2511"),
            "output_dir": str(output_dir),
        }

    qwen_params = config.get("step_2", {}).get("defaults", {})
    cost_per_image = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    model_label = config.get("model_label", "Qwen-Image-Edit-2511")

    # ---------- Copy reference files for self-containment ----------
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

    # ---------- Run Qwen Step 2 ----------
    qwen_out_path = output_dir / "05_step2_qwen_final.jpg"
    qwen_meta: dict = {}
    final_status = "success"
    error_message = None

    try:
        qwen_meta = step_2_qwen_edit.generate(
            step_1_local_path=str(output_dir / "03_step1_persona.jpg"),
            step_2_prompt=step_2_prompt_text,
            fal_qwen_params=qwen_params,
            out_path=qwen_out_path,
            scenario_id=scenario_id,
        )
        qwen_meta["cost_usd"] = cost_per_image
    except Exception as e:
        final_status = "failed"
        error_message = str(e)
        qwen_meta = {"error": error_message, "endpoint": "fal-ai/qwen-image-edit-2511"}
        print(f"[{scenario_id}] FAILED: {e}")

    (output_dir / "05_step2_qwen_meta.json").write_text(
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
        "output_dir": str(output_dir),
    }
    batch_trace.write_chain_html(output_dir, record)

    return record


# ──────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-run Qwen-Image-Edit-2511 Step 2 against an entire Plan A run."
    )
    parser.add_argument(
        "--reuse-run-root",
        type=Path,
        required=True,
        help="path to a Plan A run directory containing one subdir per scenario, "
             "e.g. outputs/runs/2026-05-08_17-04-15_plan_a",
    )
    parser.add_argument(
        "--only", nargs="*", default=None, metavar="SCENARIO_ID",
        help="restrict to these scenario IDs (default: all discovered)",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=None, metavar="SCENARIO_ID",
        help="skip these scenario IDs",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="skip the cost-confirmation prompt",
    )
    parser.add_argument(
        "--rebuild-prompt", action="store_true",
        help="regenerate each Step 2 prompt via Opus 4.7 (default: reuse baseline)",
    )
    args = parser.parse_args()

    root: Path = args.reuse_run_root
    if not root.exists() or not root.is_dir():
        print(f"[batch] reuse-run-root does not exist: {root}")
        return 1

    # ---------- Discover scenarios ----------
    scenario_dirs = _discover_scenario_dirs(root)
    if not scenario_dirs:
        print(f"[batch] no valid scenario subdirectories found under {root}")
        print(f"[batch] expected each subdir to contain: {', '.join(REQUIRED_FILES)}")
        return 1

    if args.only:
        keep = set(args.only)
        scenario_dirs = [d for d in scenario_dirs if d.name in keep]
    if args.exclude:
        skip = set(args.exclude)
        scenario_dirs = [d for d in scenario_dirs if d.name not in skip]

    n = len(scenario_dirs)
    if n == 0:
        print("[batch] no scenarios left after filtering")
        return 1

    config = _load_config()
    cost_per_image = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    estimated_cost = n * cost_per_image
    model_label = config.get("model_label", "Qwen-Image-Edit-2511")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    batch_dir = OUTPUT_ROOT / f"{timestamp}_batch"

    # ---------- Confirm before spending ----------
    print(f"[batch] reuse-run-root:  {root}")
    print(f"[batch] scenarios found: {n}")
    print(f"[batch] estimated cost:  ${estimated_cost:.2f}")
    print(f"[batch] est. wall time:  ~{n * 30 // 60} min ({n * 30}s sequential @ ~30s each)")
    print(f"[batch] output dir:      {batch_dir}")
    print(f"[batch] model:           {model_label}")

    if not args.yes:
        try:
            confirm = input("\n[batch] proceed? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[batch] aborted")
            return 0
        if confirm not in ("y", "yes"):
            print("[batch] aborted")
            return 0

    batch_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Process scenarios sequentially ----------
    records: list[dict] = []
    t_start = time.time()
    interrupted = False

    try:
        for i, scenario_dir in enumerate(scenario_dirs, start=1):
            scenario_id = scenario_dir.name
            print(f"\n[batch] [{i}/{n}] {scenario_id}")
            sub_output_dir = batch_dir / scenario_id

            try:
                record = _process_scenario(
                    reuse_dir=scenario_dir,
                    output_dir=sub_output_dir,
                    config=config,
                    rebuild_prompt=args.rebuild_prompt,
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[batch]   FATAL in {scenario_id}: {e}")
                record = {
                    "scenario": {"id": scenario_id},
                    "final_status": "failed",
                    "error_message": f"unhandled exception: {e}",
                    "reused_run_path": str(scenario_dir),
                    "experiment": EXPERIMENT_NAME,
                    "model_label": model_label,
                    "output_dir": str(sub_output_dir),
                }

            records.append(record)
            status = record.get("final_status")
            if status == "success":
                qmeta = record.get("step_2_qwen_meta") or {}
                print(
                    f"[batch]   OK  {qmeta.get('elapsed_seconds', 0):.1f}s "
                    f"${qmeta.get('cost_usd', 0):.3f}"
                )
            else:
                print(f"[batch]   FAIL: {record.get('error_message')}")

    except KeyboardInterrupt:
        interrupted = True
        print(f"\n[batch] interrupted after {len(records)}/{n} scenarios")
        print("[batch] writing partial results...")

    elapsed = time.time() - t_start

    # ---------- Aggregate ----------
    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    actual_cost = sum(
        (r.get("step_2_qwen_meta") or {}).get("cost_usd", 0)
        for r in records
        if r.get("final_status") == "success"
    )

    summary = {
        "experiment": EXPERIMENT_NAME,
        "model_label": model_label,
        "timestamp": timestamp,
        "reuse_run_root": str(root),
        "rebuild_prompt": bool(args.rebuild_prompt),
        "interrupted": interrupted,
        "total_discovered": n,
        "completed": len(records),
        "succeeded": succeeded,
        "failed": failed,
        "actual_cost_usd": round(actual_cost, 4),
        "elapsed_seconds": round(elapsed, 1),
    }

    (batch_dir / "batch_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    light_records = []
    for r in records:
        light_records.append({
            "scenario_id": r.get("scenario", {}).get("id"),
            "category": r.get("scenario", {}).get("category"),
            "archetype": r.get("scenario", {}).get("archetype"),
            "difficulty": r.get("scenario", {}).get("difficulty"),
            "final_status": r.get("final_status"),
            "error_message": r.get("error_message"),
            "qwen_elapsed": (r.get("step_2_qwen_meta") or {}).get("elapsed_seconds"),
            "qwen_cost": (r.get("step_2_qwen_meta") or {}).get("cost_usd"),
            "qwen_seed": (r.get("step_2_qwen_meta") or {}).get("seed"),
            "output_dir": r.get("output_dir"),
        })
    (batch_dir / "all_records.json").write_text(
        json.dumps(light_records, indent=2), encoding="utf-8"
    )

    # ---------- Overview HTML ----------
    batch_trace.write_overview_html(batch_dir, records, summary)

    # ---------- Final summary ----------
    print("")
    print("=" * 60)
    print(f"[batch] DONE")
    print(f"[batch]   completed:   {len(records)}/{n}")
    print(f"[batch]   succeeded:   {succeeded}")
    print(f"[batch]   failed:      {failed}")
    print(f"[batch]   actual cost: ${actual_cost:.2f}")
    print(f"[batch]   elapsed:     {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"[batch]   overview:    {batch_dir / 'overview.html'}")
    print("=" * 60)

    return 0 if failed == 0 and not interrupted else 2


if __name__ == "__main__":
    sys.exit(main())