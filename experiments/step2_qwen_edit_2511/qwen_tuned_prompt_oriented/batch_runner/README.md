# batch_runner — qwen_tuned_prompt_oriented

Batch CLI for the `qwen_tuned_prompt_oriented` experiment. Runs all 30 (or a filtered subset) Plan A scenarios through:

1. Step 2 prompt regeneration via Opus 4.7 + this experiment's `master_prompt_step2_qwen.md`
2. Hidden orientation-picker layer (Opus 4.7 + `orientation_picker_prompt.md`) → picks `horizontal` / `vertical` / `45_right` / `45_left`
3. Qwen Image Edit 2511 call with the chosen pre-rotated product file as `image_urls[1]`
4. Per-scenario `chain.html` + batch-level `overview.html`

## Pre-flight check

Before any API call is made, the runner verifies all 4 product orientation files exist at the project root:

```
assets/product_horizontal.jpg
assets/product_vertical.jpg
assets/product_45_right.jpg
assets/product_45_left.jpg
```

If any is missing, the runner halts with a clear error and zero spend.

## Quick reference

| Flag | Required? | Default | Description |
|------|-----------|---------|-------------|
| `--plan-a-root` | yes | — | path to a completed Plan A run dir (the one containing 30 scenario subdirs) |
| `--qwen-v1-root` | optional | none | path to a previous `step2_qwen_edit_2511` batch dir (for the v1 panel in A/B/C view) |
| `--only` | optional | all | comma-separated scenario IDs to include |
| `--exclude` | optional | none | comma-separated scenario IDs to skip |
| `--yes` | optional | false | skip cost confirmation prompt |

## Examples

### Full 30-scenario run with both reference batches available

Run from project root `D:\video_automation_prototype\New_Image_flow`:

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch
```

You'll see a cost confirmation:

```
[batch] scenarios:       30
[batch] per scenario:    $0.240 = $0.040 qwen + $0.180 opus + $0.020 picker
[batch] estimated cost:  $7.20
[batch] est. wall time:  ~17 min (1050s sequential)
[batch] proceed? (y/n):
```

Type `y` to start.

### Run a single problem scenario

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch --only bedroom_robe_with_product_13 --yes
```

Useful for testing the picker on a known-failure scenario.

### Run a small subset

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch --only bedroom_robe_with_product_13,kitchen_matcha_morning_handheld_16,outdoor_golden_hour_patio_27
```

### Skip flat-lay scenarios (no persona)

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --exclude kitchen_island_overhead_flat_lay_17,bathroom_marble_counter_flat_lay_20,bedroom_bedside_flat_lay_14
```

## What you get back

```
batch_runner/outputs/<timestamp>_batch/
├── overview.html                ← top-level 3-up A/B/C grid, refreshed every 5 scenarios
├── batch_manifest.json          ← machine-readable summary (status, orientations, seeds, word counts)
└── <scenario_id>/                  (one per scenario)
    ├── chain.html                  ← drill-down with 5 panels + click-to-zoom + orientation reasoning
    ├── 01_scenario.yaml            (copied from plan-a)
    ├── 02_step1_prompt.json        (copied)
    ├── 03_step1_persona.jpg        (copied)
    ├── 04_step2_nb_prompt.json     (copied — for OLD/NEW prompt diff)
    ├── 04_step2_qwen_prompt.json   (NEW — Qwen-tuned, orientation-agnostic)
    ├── 04b_orientation_picker.json (NEW — picker decision + reasoning)
    ├── 05_step2_nb.jpg             (copied — NB baseline)
    ├── 05_step2_qwen_v1.jpg        (copied — Qwen with OLD NB-shaped prompt)
    └── 05_step2_qwen_v2.jpg        (NEW — Qwen v2 with NEW prompt + picked orientation)
```

The `overview.html` 3-up cards show NB / Qwen-v1 / Qwen-v2. The Qwen-v2 thumbnail has a purple corner pill showing the picked orientation (`horizontal` / `vertical` / `45_right` / `45_left`), so you can scan the grid and immediately see the orientation distribution.

`batch_manifest.json` is your friend for post-run analysis — every record has `picked_orientation`, `picker_reasoning`, `final_status`, `qwen_v2_seed`, and `step_2_qwen_word_count`.

## Behavior during the run

- **Per-scenario fail-safe.** If any single scenario crashes (Qwen API error, Opus timeout, file write failure), it's marked failed and the batch continues. Failed scenarios show with a red badge and the error message in `chain.html`.
- **Mid-batch overview refresh.** Every 5 completed scenarios, `overview.html` and `batch_manifest.json` are rewritten with what's done so far. You can refresh the page in your browser while the batch runs to see progress.
- **Ctrl+C is safe.** Triggers a clean shutdown that writes a partial overview tagged `(interrupted)`. Anything completed before Ctrl+C is preserved with full HTML + JSON.

## Troubleshooting

**"product orientation files missing — run halted before any API calls"**
You're missing one or more of `assets/product_horizontal.jpg`, `assets/product_vertical.jpg`, `assets/product_45_right.jpg`, `assets/product_45_left.jpg` at the project root. Check the printed paths and confirm the files exist with those exact names.

**"baseline reuse-run dir missing required files"**
The `--plan-a-root` you provided contains a scenario subdir that doesn't have all 4 baseline files (`01_scenario.yaml`, `02_step1_prompt.json`, `03_step1_persona.jpg`, `04_step2_prompt.json`). That scenario will be marked failed and the batch continues. Either skip it with `--exclude` or check why the baseline run is incomplete.

**"Opus prompt regeneration failed"**
Most commonly: `ANTHROPIC_API_KEY` not set, network timeout, or hitting Opus rate limits. If it's a rate-limit issue, re-run with `--only <failed_scenarios>` after a brief wait. The cache for fal uploads is preserved across runs, so re-runs only re-pay the Opus + Qwen costs for the affected scenarios.

**"orientation picker failed"**
The picker has a defensive fallback to `horizontal` on JSON parse errors, so this is rare. If it fires, the scenario is marked failed (no Qwen call attempted, since the orientation choice drives which file gets uploaded). Re-run that scenario with `--only`.

**Qwen call returns no images**
Almost always a fal API transient. Re-run with `--only <failed_scenarios>`.

**The overview.html shows v1 panels are blank for all scenarios**
You forgot `--qwen-v1-root` or the path is wrong. Re-run with the correct path; the v1 panel is just a comparison reference (NOT regenerated by this batch) so it has no API cost.

**Path errors on Windows**
Use forward slashes in the CLI args (`outputs/runs/...`) — Python normalizes them. PowerShell line continuation with backtick (`` ` ``) is fragile; prefer single-line commands like the examples above.

## What this runner does NOT do

- Re-run Stage 1 (PuLID). It reuses `03_step1_persona.jpg` from the Plan A baseline.
- Re-run the Nano Banana Step 2. It reuses `05_step2_final.jpg` from the Plan A baseline as the NB reference panel.
- Re-run the previous Qwen-v1 batch. It copies `05_step2_qwen_final.jpg` from `--qwen-v1-root` if provided.
- Modify any file in `experiments/step2_qwen_edit_2511/` outside `qwen_tuned_prompt_oriented/`.
- Modify `assets/product.jpg` or any file in `prompts/`, `src/`, `pipelines/`, `config/`, `scenarios/`.
- Run scenarios in parallel. Sequential is intentional — keeps fal rate limits respected and Opus costs predictable.

Strictly additive. Sandboxed.