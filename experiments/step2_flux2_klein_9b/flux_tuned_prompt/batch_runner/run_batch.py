"""
experiments/step2_flux2_klein_9b/flux_tuned_prompt/batch_runner/run_batch.py

Batch runner for the flux_tuned_prompt experiment (--plan-a-root mode).

Reuses Stage 1 (PuLID) and Step 2 NB baseline outputs from a prior Plan A
run, then re-runs Step 2 with the FLUX-tuned prompt + FLUX-2 Klein 9B Base
Edit. Generates A/B comparison overview vs the NB baseline.

Pipeline per scenario:
  1. Validate Plan A baseline files exist
  2. Opus 4.7 + master_prompt_step2_flux.md → FLUX-tuned Step 2 prompt
                                              + negative_prompt + fal_flux_params
  3. Copy NB baseline image for A/B comparison
  4. FLUX-2 Klein 9B Base Edit call with persona + assets/product.jpg
  5. Per-scenario chain.html via trace_html_batch
  6. Batch overview.html via trace_html_batch (2-up grid: NB / FLUX)

Output dir:
  experiments/step2_flux2_klein_9b/flux_tuned_prompt/batch_runner/outputs/<timestamp>_batch/

Usage (from project root):

    python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a

Optional flags:
    --only bedroom_robe_with_product_13,kitchen_matcha_morning_handheld_16
    --exclude flat_lay,gym_bag_open_lineup_05
    --yes
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

from experiments.step2_flux2_klein_9b.flux_tuned_prompt import run as exp_run
from experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner import (
    trace_html_batch as batch_trace,
)


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
BATCH_OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"
PRODUCT_JPG = PROJECT_ROOT / "assets" / "product.jpg"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _verify_inputs() -> None:
    """Fail loudly BEFORE any API call if required inputs are missing."""
    problems = []
    if not PRODUCT_JPG.exists():
        problems.append(f"missing product reference: {PRODUCT_JPG}")
    flux_master = EXPERIMENT_DIR / "master_prompt_step2_flux.md"
    if not flux_master.exists():
        problems.append(f"missing FLUX-tuned master prompt: {flux_master}")
    import os
    if not os.getenv("FAL_KEY"):
        problems.append("FAL_KEY not set in environment (.env)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY not set in environment (.env)")

    if problems:
        msg = "[batch] pre-flight check failed — run halted before any API calls:\n  " + "\n  ".join(problems)
        raise RuntimeError(msg)


def _discover_scenarios(plan_a_root: Path) -> list[Path]:
    if not plan_a_root.exists() or not plan_a_root.is_dir():
        raise FileNotFoundError(f"--plan-a-root not found: {plan_a_root}")
    candidates = sorted([p for p in plan_a_root.iterdir() if p.is_dir()])
    return [c for c in candidates if (c / "01_scenario.yaml").exists()]


def _filter_scenarios(scenarios, only, exclude):
    if only:
        only_set = set(only)
        scenarios = [s for s in scenarios if s.name in only_set]
    if exclude:
        excl_set = set(exclude)
        scenarios = [s for s in scenarios if s.name not in excl_set]
    return scenarios


def _confirm_cost(n: int, config: dict, yes: bool) -> bool:
    cost_flux = config.get("step_2", {}).get("cost_per_image_usd", 0.05)
    cost_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.15)
    per = cost_flux + cost_opus
    total = per * n
    # Estimate wall time: FLUX 9b/base/edit (28 steps) takes ~15-25s per image
    # plus ~10s for Opus prompt = ~30s per scenario
    est_seconds = n * 30

    print("")
    print(f"[batch] scenarios:       {n}")
    print(
        f"[batch] per scenario:    ${per:.3f} = ${cost_flux:.3f} flux + "
        f"${cost_opus:.3f} opus"
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
    records: list,
    plan_a_root: Path,
    config: dict,
    started_at: float,
    interrupted: bool,
) -> None:
    cost_flux = config.get("step_2", {}).get("cost_per_image_usd", 0.05)
    cost_opus = config.get("step_2", {}).get("cost_per_prompt_opus_usd", 0.15)
    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    actual_cost = succeeded * (cost_flux + cost_opus) + failed * cost_opus

    summary = {
        "succeeded": succeeded,
        "failed": failed,
        "actual_cost_usd": round(actual_cost, 3),
        "elapsed_seconds": time.time() - started_at,
        "timestamp": batch_dir.name,
        "model_label": config.get("model_label", "FLUX (tuned)"),
        "reuse_run_root": str(plan_a_root),
        "interrupted": interrupted,
        "is_full_run": False,
    }
    batch_trace.write_overview_html(batch_dir, records, summary)

    manifest = {
        **summary,
        "scenario_records": [
            {
                "scenario_id": r.get("scenario", {}).get("id", "?"),
                "final_status": r.get("final_status"),
                "error_message": r.get("error_message"),
                "flux_elapsed_s": (r.get("step_2_flux_meta") or {}).get(
                    "elapsed_seconds"
                ),
                "flux_seed": (r.get("step_2_flux_meta") or {}).get("seed"),
                "step_2_flux_word_count": r.get("step_2_flux_prompt", {}).get(
                    "word_count"
                ),
                "negative_prompt_present": bool(
                    r.get("step_2_flux_prompt", {}).get("negative_prompt", "").strip()
                ),
                "guidance_scale": r.get("step_2_flux_prompt", {})
                .get("fal_flux_params", {})
                .get("guidance_scale"),
            }
            for r in records
        ],
    }
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch runner for the flux_tuned_prompt experiment "
                    "(--plan-a-root mode, A/B vs NB baseline)."
    )
    parser.add_argument("--plan-a-root", type=Path, required=True,
                        help="path to a completed Plan A run dir (contains the 30 scenario subdirs)")
    parser.add_argument("--only", type=str, default=None)
    parser.add_argument("--exclude", type=str, default=None)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    config = _load_config()
    try:
        _verify_inputs()
    except RuntimeError as e:
        print(str(e))
        return 1

    plan_a_root: Path = args.plan_a_root.resolve()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    exclude = [s.strip() for s in args.exclude.split(",")] if args.exclude else None

    try:
        all_scenarios = _discover_scenarios(plan_a_root)
    except FileNotFoundError as e:
        print(f"[batch] {e}")
        return 1

    scenarios = _filter_scenarios(all_scenarios, only, exclude)
    if not scenarios:
        print(f"[batch] no scenarios to run after filtering ({len(all_scenarios)} available)")
        return 1

    if not _confirm_cost(len(scenarios), config, args.yes):
        print("[batch] aborted by user")
        return 0

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    batch_dir = BATCH_OUTPUT_ROOT / f"{timestamp}_batch"
    batch_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print(f"[batch] output dir:       {batch_dir}")
    print(f"[batch] plan-a-root:      {plan_a_root}")
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

            try:
                record = exp_run.process_scenario(scenario_dir, output_dir, config)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[batch]   {sc_id}: UNEXPECTED CRASH: {e}")
                record = {
                    "scenario": {"id": sc_id},
                    "final_status": "failed",
                    "error_message": f"unhandled exception: {e}",
                    "experiment": exp_run.EXPERIMENT_NAME,
                    "model_label": config.get("model_label", "FLUX (tuned)"),
                }

            try:
                batch_trace.write_chain_html(output_dir, record)
            except Exception as e:
                print(f"[batch]   {sc_id}: chain.html write failed: {e}")

            records.append(record)

            elapsed = time.time() - scenario_started
            status = record.get("final_status", "?")
            wc = record.get("step_2_flux_prompt", {}).get("word_count", "—")
            print(
                f"[batch]   {sc_id}: {status.upper()} in {elapsed:.1f}s "
                f"(prompt: {wc} words)"
            )

            if i % 5 == 0:
                _write_partial_overview(
                    batch_dir, records, plan_a_root, config,
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

    _write_partial_overview(
        batch_dir, records, plan_a_root, config, started_at,
        interrupted=interrupted,
    )

    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    elapsed_total = time.time() - started_at

    print("")
    print("[batch] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[batch] DONE{'  (interrupted)' if interrupted else ''}")
    print(f"[batch]   succeeded:     {succeeded} / {len(records)}")
    print(f"[batch]   failed:        {failed}")
    print(f"[batch]   wall time:     {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")
    print(f"[batch]   overview.html: {batch_dir / 'overview.html'}")
    print(f"[batch]   manifest.json: {batch_dir / 'batch_manifest.json'}")
    print("[batch] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return 0 if (failed == 0 and not interrupted) else 2


if __name__ == "__main__":
    sys.exit(main())