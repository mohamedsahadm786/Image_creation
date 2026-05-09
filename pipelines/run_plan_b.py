"""
run_plan_b.py — Plan B pipeline orchestrator.

Plan B is identical to Plan A except Step 1 uses fal-ai/flux-pro/kontext
with the cropped persona_face_only.jpg as reference instead of PuLID with
the full persona.jpg. Used as backup if Plan A's outfit override is weak.

Same args as run_plan_a.py.
"""

import argparse
import json
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db, scenario_loader, prompt_builder, step_1, step_2, trace_html


PLAN = "plan_b"
RUN_BASE = Path("outputs/runs")


def main() -> int:
    args = _parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = f"{timestamp}_{PLAN}"
    run_dir = RUN_BASE / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    all_scenarios = scenario_loader.load_scenarios()
    if args.only:
        scenarios = [s for s in all_scenarios if s["id"] == args.only]
        if not scenarios:
            print(f"ERROR: scenario id not found: {args.only}")
            return 1
        mode_label = f"single ({args.only})"
    elif args.pilot:
        scenarios = scenario_loader.filter_pilot_scenarios(all_scenarios)
        mode_label = f"pilot ({len(scenarios)})"
    else:
        scenarios = all_scenarios
        mode_label = f"full ({len(scenarios)})"

    print(f"\n{'=' * 72}")
    print(f" ALLUVI v2 — PLAN B RUN: {run_id}")
    print(f" Step 1 endpoint: fal-ai/flux-pro/kontext (face-only crop)")
    print(f" Mode: {mode_label}")
    print(f" Output dir: {run_dir}")
    print(f"{'=' * 72}\n")

    db.create_run(run_id=run_id, plan=PLAN, pilot_mode=args.pilot, notes=f"mode={mode_label}")

    records, run_t0 = [], time.time()
    success_count = failure_count = 0
    total_cost = 0.0

    for i, scenario in enumerate(scenarios, 1):
        sc_id = scenario["id"]
        print(f"\n{'─' * 72}\n [{i}/{len(scenarios)}] {sc_id}\n{'─' * 72}")
        scenario_dir = run_dir / sc_id
        scenario_dir.mkdir(parents=True, exist_ok=True)
        gen_id = uuid.uuid4().hex
        db.create_generation(gen_id, run_id, sc_id, PLAN)

        (scenario_dir / "01_scenario.yaml").write_text(
            json.dumps(scenario, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        record = {
            "scenario": scenario, "plan": PLAN, "gen_id": gen_id, "run_id": run_id,
            "step_1_output": None, "step_2_output": None,
            "step_1_image": None, "step_2_image": None,
            "final_status": "pending", "error_message": None,
        }

        try:
            step_1_output = prompt_builder.build_step_1_prompt(scenario)
            (scenario_dir / "02_step1_prompt.json").write_text(
                json.dumps(step_1_output, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            record["step_1_output"] = step_1_output
            db.update_step_1(gen_id, status="prompt_built",
                             prompt=step_1_output.get("step_1_image_prompt", ""))

            # Plan B-specific param shape (Kontext, not PuLID)
            kontext_params = {
                "aspect_ratio": "9:16",
                "guidance_scale": step_1_output.get("fal_pulid_params", {}).get("guidance_scale", 3.5),
                "num_inference_steps": 30,
                "output_format": "jpeg",
            }

            step_1_image_path = scenario_dir / "03_step1_persona.jpg"
            step_1_meta = step_1.generate(
                plan=PLAN,
                step_1_prompt=step_1_output["step_1_image_prompt"],
                step_1_params=kontext_params,
                out_path=step_1_image_path,
                scenario_id=sc_id,
            )
            (scenario_dir / "03_step1_meta.json").write_text(
                json.dumps(step_1_meta, indent=2), encoding="utf-8"
            )
            record["step_1_image"] = str(step_1_image_path)
            db.update_step_1(gen_id, status="success", endpoint=step_1_meta["endpoint"],
                             image_path=str(step_1_image_path), request_id=step_1_meta["request_id"],
                             seed=step_1_meta["seed"], cost_usd=step_1_meta["cost_usd"],
                             elapsed_s=step_1_meta["elapsed_seconds"])
            total_cost += step_1_meta["cost_usd"]

            step_2_output = prompt_builder.build_step_2_prompt(scenario, step_1_output)
            (scenario_dir / "04_step2_prompt.json").write_text(
                json.dumps(step_2_output, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            record["step_2_output"] = step_2_output
            db.update_step_2(gen_id, status="prompt_built",
                             prompt=step_2_output.get("step_2_image_prompt", ""))

            step_2_image_path = scenario_dir / "05_step2_final.jpg"
            step_2_meta = step_2.generate(
                plan=PLAN,
                step_1_local_path=str(step_1_image_path),
                step_2_prompt=step_2_output["step_2_image_prompt"],
                step_2_params=step_2_output.get("fal_nano_banana_params", {}),
                out_path=step_2_image_path,
                scenario_id=sc_id,
            )
            (scenario_dir / "05_step2_meta.json").write_text(
                json.dumps(step_2_meta, indent=2), encoding="utf-8"
            )
            record["step_2_image"] = str(step_2_image_path)
            db.update_step_2(gen_id, status="success", endpoint=step_2_meta["endpoint"],
                             image_path=str(step_2_image_path), request_id=step_2_meta["request_id"],
                             seed=step_2_meta["seed"], cost_usd=step_2_meta["cost_usd"],
                             elapsed_s=step_2_meta["elapsed_seconds"])
            total_cost += step_2_meta["cost_usd"]

            record["final_status"] = "success"
            db.finalize_generation(gen_id, "success")
            success_count += 1
            print(f"  ✓ {sc_id} complete")

        except Exception as e:
            record["final_status"] = "failed"
            record["error_message"] = f"{type(e).__name__}: {e}"
            db.finalize_generation(gen_id, "failed", record["error_message"])
            failure_count += 1
            print(f"  ✗ {sc_id} FAILED: {record['error_message']}")
            traceback.print_exc()

        finally:
            try:
                trace_html.write_chain_html(scenario_dir, record)
            except Exception:
                pass
            records.append(record)

    duration = int(time.time() - run_t0)
    metadata = {
        "run_id": run_id, "timestamp": timestamp, "plan": PLAN,
        "pilot_mode": args.pilot,
        "total_scenarios": len(records), "successful": success_count, "failed": failure_count,
        "total_cost_usd": round(total_cost, 4), "duration_seconds": duration,
    }
    (run_dir / "run_summary.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (run_dir / "all_records.json").write_text(
        json.dumps(records, indent=2, default=str), encoding="utf-8"
    )
    trace_html.write_overview_html(run_dir, records, metadata)
    db.finalize_run(run_id, len(records), success_count, failure_count, total_cost, duration)

    print(f"\n{'=' * 72}")
    print(f" PLAN B RUN COMPLETE: {run_id}")
    print(f"{'=' * 72}")
    print(f" Successful : {success_count}/{len(records)}")
    print(f" Failed     : {failure_count}")
    print(f" Total cost : ${total_cost:.2f}")
    print(f" Duration   : {duration // 60}m {duration % 60}s")
    print(f" Overview   : {run_dir / 'overview.html'}\n")
    return 0 if failure_count == 0 else 1


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Alluvi v2 Plan B (Kontext face-crop + Nano Banana 2)")
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--only", type=str, default=None)
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())