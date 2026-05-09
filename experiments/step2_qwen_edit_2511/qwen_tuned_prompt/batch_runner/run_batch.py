"""
run_batch.py — batch Qwen-tuned-prompt Step 2 swap.

Self-contained. Does NOT depend on or modify the parent run.py / trace_html.py
or any sibling experiment. Imports only the unchanged step_2_qwen_edit.py for
the fal API call, prompt_builder_qwen.py for the Opus prompt regeneration,
and this folder's trace_html_batch.py for the 3-up A/B/C grid.

Pipeline per scenario:
  1. Read scenario, step_1_prompt, NB baseline image, NB baseline prompt
     from --plan-a-root/<scenario_id>/
  2. Read Qwen-v1 image (Qwen with OLD NB-shaped prompt) from
     --qwen-v1-root/<scenario_id>/  (optional but recommended for A/B/C)
  3. Call Opus 4.7 with master_prompt_step2_qwen.md → NEW Step 2 prompt
  4. Call Qwen with the NEW prompt → 05_step2_qwen_v2.jpg
  5. Generate chain.html with 5 panels and 3-up A/B/C strip

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch \\
        --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a \\
        --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch

Optional:
    --only id1 id2 ...        only run these scenario IDs
    --exclude id1 id2 ...     skip these scenario IDs
    --yes                     skip the cost-confirmation prompt

The --qwen-v1-root is OPTIONAL but recommended — without it the v1 panel will
show "—" in the overview grid and "not provided" in chain.html.

Output:
    experiments/step2_qwen_edit_2511/qwen_tuned_prompt/batch_runner/outputs/<timestamp>_batch/
        overview.html              (3-up A/B/C grid — open this first)
        batch_summary.json
        all_records.json
        <scenario_id>/
            01_scenario.yaml
            02_step1_prompt.json
            03_step1_persona.jpg
            04_step2_nb_prompt.json     (OLD NB-shaped prompt — copied)
            04_step2_qwen_prompt.json   (NEW Qwen-tuned prompt — generated)
            05_step2_nb.jpg             (NB baseline — copied)
            05_step2_nb_meta.json       (copied)
            05_step2_qwen_v1.jpg        (Qwen with OLD prompt — copied if available)
            05_step2_qwen_v1_meta.json  (copied if available)
            05_step2_qwen_v2.jpg        (NEW — Qwen with NEW prompt)
            05_step2_qwen_v2_meta.json  (NEW)
            chain.html                  (5-panel A/B/C drill-down)
"""

import argparse
import json
import shutil
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

# Project root is 5 levels up from this file:
#   batch_runner/run_batch.py
#     ↑ batch_runner
#       ↑ qwen_tuned_prompt
#         ↑ step2_qwen_edit_2511
#           ↑ experiments
#             ↑ project_root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse the existing Qwen API caller (UNCHANGED)
from experiments.step2_qwen_edit_2511 import step_2_qwen_edit
# This experiment's own modules
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt import prompt_builder_qwen
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner import (
    trace_html_batch as batch_trace,
)


EXPERIMENT_NAME = "step2_qwen_edit_2511_with_qwen_tuned_prompt"

BATCH_RUNNER_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = BATCH_RUNNER_DIR.parent
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
OUTPUT_ROOT = BATCH_RUNNER_DIR / "outputs"

REQUIRED_FILES = (
    "01_scenario.yaml",
    "02_step1_prompt.json",
    "03_step1_persona.jpg",
    "04_step2_prompt.json",
)


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


def _process_scenario(
    reuse_dir: Path,
    output_dir: Path,
    config: dict,
    qwen_v1_dir: Path | None,
) -> dict:
    """
    Run qwen_tuned_prompt pipeline for one scenario.
    Returns a record dict — never raises (caller manages the loop).
    """
    scenario_id = reuse_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    missing = [f for f in REQUIRED_FILES if not (reuse_dir / f).exists()]
    if missing:
        return {
            "scenario": {"id": scenario_id},
            "final_status": "failed",
            "error_message": f"baseline reuse-run dir missing required files: {missing}",
            "reused_run_path": str(reuse_dir),
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen (qwen-tuned prompt)"),
            "output_dir": str(output_dir),
        }

    scenario = _load_yaml(reuse_dir / "01_scenario.yaml")
    step_1_output = _load_json(reuse_dir / "02_step1_prompt.json")
    nb_step_2_output = _load_json(reuse_dir / "04_step2_prompt.json")

    # ---------- Generate NEW Qwen-tuned Step 2 prompt via Opus ----------
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
            "qwen_v1_reused_path": str(qwen_v1_dir) if qwen_v1_dir else None,
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen (qwen-tuned prompt)"),
            "output_dir": str(output_dir),
        }

    qwen_step_2_prompt_text = qwen_step_2_output.get("step_2_image_prompt", "").strip()
    if not qwen_step_2_prompt_text:
        return {
            "scenario": scenario,
            "final_status": "failed",
            "error_message": "Qwen-tuned step_2_image_prompt is empty in the prompt JSON",
            "reused_run_path": str(reuse_dir),
            "qwen_v1_reused_path": str(qwen_v1_dir) if qwen_v1_dir else None,
            "experiment": EXPERIMENT_NAME,
            "model_label": config.get("model_label", "Qwen (qwen-tuned prompt)"),
            "output_dir": str(output_dir),
        }

    # ---------- Save / copy reference files ----------
    shutil.copy(reuse_dir / "01_scenario.yaml", output_dir / "01_scenario.yaml")
    shutil.copy(reuse_dir / "02_step1_prompt.json", output_dir / "02_step1_prompt.json")
    shutil.copy(reuse_dir / "03_step1_persona.jpg", output_dir / "03_step1_persona.jpg")

    (output_dir / "04_step2_nb_prompt.json").write_text(
        json.dumps(nb_step_2_output, indent=2), encoding="utf-8"
    )
    (output_dir / "04_step2_qwen_prompt.json").write_text(
        json.dumps(qwen_step_2_output, indent=2), encoding="utf-8"
    )

    # ---------- Copy NB baseline ----------
    nano_banana_meta = None
    nb_image_path = reuse_dir / "05_step2_final.jpg"
    nb_meta_path = reuse_dir / "05_step2_meta.json"
    if nb_image_path.exists():
        shutil.copy(nb_image_path, output_dir / "05_step2_nb.jpg")
    if nb_meta_path.exists():
        shutil.copy(nb_meta_path, output_dir / "05_step2_nb_meta.json")
        try:
            nano_banana_meta = _load_json(nb_meta_path)
        except Exception:
            nano_banana_meta = None

    # ---------- Copy Qwen-v1 (Qwen with OLD NB-shaped prompt) ----------
    qwen_v1_meta = None
    if qwen_v1_dir is not None:
        v1_scenario_dir = qwen_v1_dir / scenario_id
        if v1_scenario_dir.exists() and v1_scenario_dir.is_dir():
            v1_img = v1_scenario_dir / "05_step2_qwen_final.jpg"
            v1_meta = v1_scenario_dir / "05_step2_qwen_meta.json"
            if v1_img.exists():
                shutil.copy(v1_img, output_dir / "05_step2_qwen_v1.jpg")
            if v1_meta.exists():
                shutil.copy(v1_meta, output_dir / "05_step2_qwen_v1_meta.json")
                try:
                    qwen_v1_meta = _load_json(v1_meta)
                except Exception:
                    qwen_v1_meta = None

    # ---------- Run Qwen with NEW prompt ----------
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

    # ---------- Build chain.html ----------
    record = {
        "scenario": scenario,
        "step_1_output": step_1_output,
        "step_2_nb_prompt": nb_step_2_output,
        "step_2_qwen_prompt": qwen_step_2_output,
        "step_2_nb_meta": nano_banana_meta,
        "step_2_qwen_v1_meta": qwen_v1_meta,
        "step_2_qwen_v2_meta": qwen_v2_meta,
        "final_status": final_status,
        "error_message": error_message,
        "experiment": EXPERIMENT_NAME,
        "model_label": model_label,
        "reused_run_path": str(reuse_dir),
        "qwen_v1_reused_path": str(qwen_v1_dir / scenario_id) if qwen_v1_dir else None,
        "output_dir": str(output_dir),
    }
    batch_trace.write_chain_html(output_dir, record)

    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch Qwen-tuned-prompt experiment with A/B/C overview grid."
    )
    parser.add_argument(
        "--plan-a-root",
        type=Path,
        required=True,
        help="path to a Plan A run root (gives scenario.yaml, step 1, NB baseline)",
    )
    parser.add_argument(
        "--qwen-v1-root",
        type=Path,
        default=None,
        help="OPTIONAL — path to a previous step2_qwen_edit_2511 batch root "
             "(gives Qwen images generated with the OLD NB-shaped prompt). If "
             "omitted, the v1 panel/column will be empty.",
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
    args = parser.parse_args()

    plan_a_root: Path = args.plan_a_root
    if not plan_a_root.exists() or not plan_a_root.is_dir():
        print(f"[batch] --plan-a-root does not exist: {plan_a_root}")
        return 1

    qwen_v1_root: Path | None = args.qwen_v1_root
    if qwen_v1_root is not None and (not qwen_v1_root.exists() or not qwen_v1_root.is_dir()):
        print(f"[batch] WARNING: --qwen-v1-root not found, will skip v1 column: {qwen_v1_root}")
        qwen_v1_root = None

    scenario_dirs = _discover_scenario_dirs(plan_a_root)
    if not scenario_dirs:
        print(f"[batch] no valid scenario subdirectories found under {plan_a_root}")
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
    cost_per_qwen = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    cost_per_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.18)
    cost_per_scenario = cost_per_qwen + cost_per_opus
    estimated_cost = n * cost_per_scenario
    model_label = config.get("model_label", "Qwen (qwen-tuned prompt)")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    batch_dir = OUTPUT_ROOT / f"{timestamp}_batch"

    avg_call_seconds = 35  # ~5s opus + ~30s qwen
    print(f"[batch] plan-a-root:     {plan_a_root}")
    print(f"[batch] qwen-v1-root:    {qwen_v1_root if qwen_v1_root else '(none — v1 panel/column will be empty)'}")
    print(f"[batch] scenarios:       {n}")
    print(f"[batch] per scenario:    ${cost_per_scenario:.3f} = ${cost_per_qwen:.3f} qwen + ${cost_per_opus:.3f} opus")
    print(f"[batch] estimated cost:  ${estimated_cost:.2f}")
    print(f"[batch] est. wall time:  ~{n * avg_call_seconds // 60} min ({n * avg_call_seconds}s sequential)")
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
                    qwen_v1_dir=qwen_v1_root,
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
                    "qwen_v1_reused_path": str(qwen_v1_root / scenario_id) if qwen_v1_root else None,
                    "experiment": EXPERIMENT_NAME,
                    "model_label": model_label,
                    "output_dir": str(sub_output_dir),
                }

            records.append(record)
            status = record.get("final_status")
            if status == "success":
                v2 = record.get("step_2_qwen_v2_meta") or {}
                qwen_wc = record.get("step_2_qwen_prompt", {}).get("word_count", "?")
                print(
                    f"[batch]   OK  qwen {v2.get('elapsed_seconds', 0):.1f}s "
                    f"prompt {qwen_wc}w "
                    f"${v2.get('cost_total_usd', 0):.3f}"
                )
            else:
                print(f"[batch]   FAIL: {record.get('error_message')}")

    except KeyboardInterrupt:
        interrupted = True
        print(f"\n[batch] interrupted after {len(records)}/{n} scenarios")
        print("[batch] writing partial results...")

    elapsed = time.time() - t_start

    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    actual_cost = sum(
        (r.get("step_2_qwen_v2_meta") or {}).get("cost_total_usd", 0)
        for r in records
        if r.get("final_status") == "success"
    )

    summary = {
        "experiment": EXPERIMENT_NAME,
        "model_label": model_label,
        "timestamp": timestamp,
        "reuse_run_root": str(plan_a_root),
        "qwen_v1_root": str(qwen_v1_root) if qwen_v1_root else None,
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
        v2 = r.get("step_2_qwen_v2_meta") or {}
        light_records.append({
            "scenario_id": r.get("scenario", {}).get("id"),
            "category": r.get("scenario", {}).get("category"),
            "archetype": r.get("scenario", {}).get("archetype"),
            "difficulty": r.get("scenario", {}).get("difficulty"),
            "final_status": r.get("final_status"),
            "error_message": r.get("error_message"),
            "qwen_v2_elapsed": v2.get("elapsed_seconds"),
            "qwen_v2_cost_total": v2.get("cost_total_usd"),
            "qwen_v2_seed": v2.get("seed"),
            "qwen_prompt_word_count": r.get("step_2_qwen_prompt", {}).get("word_count"),
            "nb_prompt_word_count": r.get("step_2_nb_prompt", {}).get("word_count"),
            "output_dir": r.get("output_dir"),
        })
    (batch_dir / "all_records.json").write_text(
        json.dumps(light_records, indent=2), encoding="utf-8"
    )

    batch_trace.write_overview_html(batch_dir, records, summary)

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