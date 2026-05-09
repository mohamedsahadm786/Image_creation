"""
experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/batch_runner/run_batch.py

Batch runner for the qwen_tuned_prompt_oriented experiment.

Pipeline per scenario (loops over all in --plan-a-root):
  1. Validate baseline files exist
  2. Opus 4.7 + master_prompt_step2_qwen.md → orientation-agnostic Step 2 prompt
  3. Opus 4.7 + orientation_picker_prompt.md → orientation choice
  4. Resolve assets/product_<orientation>.jpg
  5. Copy NB baseline + (optional) Qwen-v1 baseline
  6. Qwen call with persona + chosen product file
  7. Per-scenario chain.html via trace_html_batch
  8. Batch overview.html via trace_html_batch (3-up grid, orientation badges)

Output dir:
  experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/batch_runner/outputs/<timestamp>_batch/

Behavior:
  - Failures in any single scenario do NOT abort the batch — the failed
    scenario gets a red badge in overview.html, others continue.
  - Ctrl+C writes a partial overview.html with "(interrupted)" tag so you
    can still see what completed.
  - Cost confirmation prompt unless --yes is passed.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch

Optional flags:
    --only bedroom_robe_with_product_13,kitchen_matcha_morning_handheld_16
    --exclude flat_lay,gym_bag_open_lineup_05
    --yes                        # skip cost confirmation prompt
"""

import argparse
import json
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import sibling modules from this experiment
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented import run as exp_run
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner import (
    trace_html_batch as batch_trace,
)


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
BATCH_OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _verify_orientation_files(config: dict) -> None:
    """Hard-fail before any API calls if any of the 4 product files is missing."""
    orientation_map = config.get("product_orientation_files", {})
    if not orientation_map:
        raise RuntimeError("config.product_orientation_files is empty")
    missing = []
    for orient, rel in orientation_map.items():
        abs_path = (PROJECT_ROOT / rel).resolve()
        if not abs_path.exists():
            missing.append(f"  {orient:<10} → {abs_path}")
    if missing:
        msg = "[batch] product orientation files missing — run halted before any API calls:\n" + "\n".join(missing)
        raise FileNotFoundError(msg)


def _discover_scenarios(plan_a_root: Path) -> list[Path]:
    """Return sorted list of scenario subdirs that have the required baseline files."""
    if not plan_a_root.exists() or not plan_a_root.is_dir():
        raise FileNotFoundError(f"--plan-a-root not found: {plan_a_root}")

    candidates = sorted([p for p in plan_a_root.iterdir() if p.is_dir()])
    valid = []
    for c in candidates:
        # process_scenario does its own deeper validation; here we just filter
        # obviously-bad candidates (no scenario.yaml at all).
        if (c / "01_scenario.yaml").exists():
            valid.append(c)
    return valid


def _filter_scenarios(
    scenarios: list[Path],
    only: list[str] | None,
    exclude: list[str] | None,
) -> list[Path]:
    if only:
        only_set = set(only)
        scenarios = [s for s in scenarios if s.name in only_set]
    if exclude:
        excl_set = set(exclude)
        scenarios = [s for s in scenarios if s.name not in excl_set]
    return scenarios


def _resolve_qwen_v1_for(scenario_dir: Path, qwen_v1_root: Path | None) -> Path | None:
    """Return matching v1 subdir under qwen_v1_root, or None if not provided / not present."""
    if qwen_v1_root is None:
        return None
    candidate = qwen_v1_root / scenario_dir.name
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


def _confirm_cost(n: int, config: dict, yes: bool) -> bool:
    cost_qwen = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    cost_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.18)
    cost_picker = config.get("step_2", {}).get("cost_per_picker_opus_usd", 0.02)
    per = cost_qwen + cost_opus + cost_picker
    total = per * n
    # rough sequential estimate: ~35s per scenario (qwen ~25s + opus ~8s + picker ~2s)
    est_seconds = n * 35

    print("")
    print(f"[batch] scenarios:       {n}")
    print(
        f"[batch] per scenario:    ${per:.3f} = ${cost_qwen:.3f} qwen + "
        f"${cost_opus:.3f} opus + ${cost_picker:.3f} picker"
    )
    print(f"[batch] estimated cost:  ${total:.2f}")
    print(f"[batch] est. wall time:  ~{est_seconds // 60} min ({est_seconds}s sequential)")

    if yes:
        print("[batch] --yes flag set, skipping confirmation")
        return True

    answer = input("[batch] proceed? (y/n): ").strip().lower()
    return answer in ("y", "yes")


def _write_partial_overview(
    batch_dir: Path,
    records: list[dict],
    plan_a_root: Path,
    qwen_v1_root: Path | None,
    config: dict,
    started_at: float,
    interrupted: bool,
) -> None:
    """Write overview.html with whatever scenarios completed so far."""
    cost_qwen = config.get("step_2", {}).get("cost_per_image_usd", 0.04)
    cost_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.18)
    cost_picker = config.get("step_2", {}).get("cost_per_picker_opus_usd", 0.02)
    per_succ = cost_qwen + cost_opus + cost_picker
    # failed scenarios still incurred opus + picker (happened before qwen) most of the time;
    # be conservative and count opus+picker for failed, full per-scenario for succeeded
    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    actual_cost = succeeded * per_succ + failed * (cost_opus + cost_picker)

    summary = {
        "succeeded": succeeded,
        "failed": failed,
        "actual_cost_usd": actual_cost,
        "elapsed_seconds": time.time() - started_at,
        "timestamp": batch_dir.name,
        "model_label": config.get("model_label", "Qwen (oriented)"),
        "reuse_run_root": str(plan_a_root),
        "qwen_v1_root": str(qwen_v1_root) if qwen_v1_root else "(none)",
        "interrupted": interrupted,
    }
    batch_trace.write_overview_html(batch_dir, records, summary)

    # Also write a JSON manifest for downstream tools
    manifest = {
        **summary,
        "scenario_records": [
            {
                "scenario_id": r.get("scenario", {}).get("id", "?"),
                "final_status": r.get("final_status"),
                "error_message": r.get("error_message"),
                "picked_orientation": (r.get("orientation_picker") or {}).get(
                    "orientation"
                ),
                "picker_reasoning": (r.get("orientation_picker") or {}).get("reasoning"),
                "qwen_v2_elapsed_s": (r.get("step_2_qwen_v2_meta") or {}).get(
                    "elapsed_seconds"
                ),
                "qwen_v2_seed": (r.get("step_2_qwen_v2_meta") or {}).get("seed"),
                "step_2_qwen_word_count": r.get("step_2_qwen_prompt", {}).get(
                    "word_count"
                ),
            }
            for r in records
        ],
    }
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch runner for the qwen_tuned_prompt_oriented experiment."
    )
    parser.add_argument(
        "--plan-a-root",
        type=Path,
        required=True,
        help="path to a completed Plan A run dir (contains the 30 scenario subdirs)",
    )
    parser.add_argument(
        "--qwen-v1-root",
        type=Path,
        default=None,
        help="OPTIONAL — path to a previous step2_qwen_edit_2511 batch dir "
             "(for the v1 panel in the A/B/C view)",
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

    # Hard-check that all 4 product files exist before doing anything expensive.
    try:
        _verify_orientation_files(config)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    plan_a_root: Path = args.plan_a_root.resolve()
    qwen_v1_root: Path | None = (
        args.qwen_v1_root.resolve() if args.qwen_v1_root else None
    )
    if qwen_v1_root is not None and (not qwen_v1_root.exists() or not qwen_v1_root.is_dir()):
        print(
            f"[batch] WARNING: --qwen-v1-root not found, will skip v1 panel: {qwen_v1_root}"
        )
        qwen_v1_root = None

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    exclude = [s.strip() for s in args.exclude.split(",")] if args.exclude else None

    # Discover + filter scenarios
    try:
        all_scenarios = _discover_scenarios(plan_a_root)
    except FileNotFoundError as e:
        print(f"[batch] {e}")
        return 1

    scenarios = _filter_scenarios(all_scenarios, only, exclude)

    if not scenarios:
        print(f"[batch] no scenarios to run after filtering ({len(all_scenarios)} available)")
        if only:
            print(f"[batch]   --only filter: {only}")
        if exclude:
            print(f"[batch]   --exclude filter: {exclude}")
        return 1

    # Cost confirmation
    if not _confirm_cost(len(scenarios), config, args.yes):
        print("[batch] aborted by user")
        return 0

    # Output dir
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    batch_dir = BATCH_OUTPUT_ROOT / f"{timestamp}_batch"
    batch_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print(f"[batch] output dir:      {batch_dir}")
    print(f"[batch] plan-a-root:     {plan_a_root}")
    print(f"[batch] qwen-v1-root:    {qwen_v1_root if qwen_v1_root else '(none)'}")
    print(f"[batch] scenarios queued: {len(scenarios)}")
    print("")

    records: list[dict] = []
    started_at = time.time()
    interrupted = False

    try:
        for i, scenario_dir in enumerate(scenarios, start=1):
            sc_id = scenario_dir.name
            scenario_started = time.time()
            print(
                f"[batch] [{i}/{len(scenarios)}] {sc_id} — starting "
                f"({i-1} done, {len(scenarios)-i+1} remaining)"
            )

            output_dir = batch_dir / sc_id
            qwen_v1_dir = _resolve_qwen_v1_for(scenario_dir, qwen_v1_root)

            try:
                record = exp_run.process_scenario(
                    scenario_dir, output_dir, config, qwen_v1_dir
                )
            except KeyboardInterrupt:
                # Bubble up so the outer try/except handles partial-overview write
                raise
            except Exception as e:
                # Defensive — process_scenario should not raise, but if it does,
                # capture as a failed record and keep going.
                print(f"[batch]   {sc_id}: UNEXPECTED CRASH: {e}")
                record = {
                    "scenario": {"id": sc_id},
                    "final_status": "failed",
                    "error_message": f"unhandled exception: {e}",
                    "experiment": exp_run.EXPERIMENT_NAME,
                    "model_label": config.get("model_label", "Qwen (oriented)"),
                }

            # Per-scenario chain.html (uses batch_trace, which has the 7-level
            # path math + back-link to overview)
            try:
                batch_trace.write_chain_html(output_dir, record)
            except Exception as e:
                print(f"[batch]   {sc_id}: chain.html write failed: {e}")

            records.append(record)

            elapsed = time.time() - scenario_started
            picker = record.get("orientation_picker") or {}
            orient = picker.get("orientation", "?")
            status = record.get("final_status", "?")
            print(
                f"[batch]   {sc_id}: {status.upper()} in {elapsed:.1f}s "
                f"(orientation: {orient})"
            )

            # Periodic partial overview after every 5 completed scenarios so
            # the user can refresh the page mid-batch and see progress
            if i % 5 == 0:
                _write_partial_overview(
                    batch_dir, records, plan_a_root, qwen_v1_root, config,
                    started_at, interrupted=False,
                )
                print(f"[batch]   (overview.html refreshed at {i}/{len(scenarios)})")

    except KeyboardInterrupt:
        interrupted = True
        print("")
        print("[batch] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("[batch] interrupted by user (Ctrl+C)")
        print(f"[batch] writing partial overview for {len(records)} completed scenarios...")
        print("[batch] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Final overview write
    _write_partial_overview(
        batch_dir, records, plan_a_root, qwen_v1_root, config, started_at,
        interrupted=interrupted,
    )

    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    elapsed_total = time.time() - started_at

    # Orientation distribution recap
    orient_counts: dict[str, int] = {}
    for r in records:
        o = (r.get("orientation_picker") or {}).get("orientation", "?")
        orient_counts[o] = orient_counts.get(o, 0) + 1

    print("")
    print("[batch] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[batch] DONE{'  (interrupted)' if interrupted else ''}")
    print(f"[batch]   succeeded:     {succeeded} / {len(records)}")
    print(f"[batch]   failed:        {failed}")
    print(f"[batch]   wall time:     {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")
    print(f"[batch]   orientations:  " + ", ".join(
        f"{k}={v}" for k, v in sorted(orient_counts.items())
    ))
    print(f"[batch]   overview.html: {batch_dir / 'overview.html'}")
    print(f"[batch]   manifest.json: {batch_dir / 'batch_manifest.json'}")
    print("[batch] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return 0 if (failed == 0 and not interrupted) else 2


if __name__ == "__main__":
    sys.exit(main())