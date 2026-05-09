# batch_runner — Qwen-tuned prompt batch runner

Self-contained batch runner for the `qwen_tuned_prompt` experiment. Does not
modify or import the parent experiment's `run.py` or `trace_html.py` or any
sibling experiment.

## What it does

For every scenario discovered under `--plan-a-root`:

1. Reads scenario.yaml, step_1_prompt.json, NB baseline image and prompt
2. Calls Opus 4.7 with `master_prompt_step2_qwen.md` → NEW Qwen-tuned Step 2 prompt
3. Copies in the matching Qwen-v1 image from `--qwen-v1-root` (if available)
4. Calls `fal-ai/qwen-image-edit-2511` with the NEW prompt → `05_step2_qwen_v2.jpg`
5. Writes per-scenario `chain.html` (5-panel A/B/C drill-down)

After all scenarios complete:

6. Writes batch-level `overview.html` — a grid of 3-up cards
   (NB / Qwen-v1 / Qwen-v2 side-by-side, Qwen-v2 purple-bordered)
7. Writes `batch_summary.json` and `all_records.json`

## CLI

```
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch [args]
```

| Flag | Required | Default | Description |
|------|:---:|---|---|
| `--plan-a-root PATH` | yes | — | Path to a Plan A run root. Provides scenario.yaml, step_1_prompt.json, 03_step1_persona.jpg, NB baseline image and prompt for each scenario. |
| `--qwen-v1-root PATH` | no | `None` | Path to a previous `step2_qwen_edit_2511` batch root. Provides Qwen images generated with the OLD NB-shaped prompt for the v1 column. If omitted, v1 column shows "—". |
| `--only ID [ID ...]` | no | all | Restrict to specific scenario IDs (space-separated, no commas). |
| `--exclude ID [ID ...]` | no | none | Skip these scenario IDs. |
| `--yes` | no | false | Skip the interactive cost-confirmation prompt. |

## Examples

### Full 30-scenario batch with A/B/C

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch `
    --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch
```

### Test on the 3 scenarios where Qwen-v1 most clearly failed

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch `
    --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch `
    --only bedroom_bed_handheld_close_11 pilates_mat_morning_handheld_09 outdoor_golden_hour_patio_27
```

### Skip the cost-confirmation prompt (CI / scripted)

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch `
    --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch `
    --yes
```

### A/B only (no v1 column — useful if you don't have a previous Qwen batch)

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch `
    --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a
```

## Output structure

```
batch_runner/outputs/<timestamp>_batch/
├── overview.html                           ← OPEN THIS — 3-up A/B/C grid
├── batch_summary.json                      ← totals + cost + elapsed
├── all_records.json                        ← per-scenario light record (CSV-able)
├── <scenario_id_1>/
│   ├── chain.html                          ← 5-panel drill-down + prompt diff
│   ├── 01_scenario.yaml                    (copied)
│   ├── 02_step1_prompt.json                (copied)
│   ├── 03_step1_persona.jpg                (copied)
│   ├── 04_step2_nb_prompt.json             (copied — OLD NB-shaped prompt)
│   ├── 04_step2_qwen_prompt.json           (NEW — Qwen-tuned prompt)
│   ├── 05_step2_nb.jpg                     (copied — NB baseline)
│   ├── 05_step2_nb_meta.json               (copied)
│   ├── 05_step2_qwen_v1.jpg                (copied — Qwen with OLD prompt)
│   ├── 05_step2_qwen_v1_meta.json          (copied)
│   ├── 05_step2_qwen_v2.jpg                (NEW — Qwen with NEW prompt)
│   └── 05_step2_qwen_v2_meta.json          (NEW)
├── <scenario_id_2>/ ...
└── <scenario_id_N>/ ...
```

Open `overview.html` first. Click any card to drill into its `chain.html`,
which shows all 5 stages plus the OLD/NEW Step 2 prompt diff side-by-side.

## Cost & timing

Per scenario:
- $0.18 — Opus 4.7 (~8K input + ~800 output tokens with Opus 4.7 pricing)
- $0.04 — Qwen API call
- **$0.22 total per scenario**
- ~5s Opus + ~30s Qwen = ~35s wall time per scenario

For 30 scenarios: **~$6.60 and ~17–18 minutes** sequential.

The runner shows a confirmation prompt with the estimate before any
API calls fire. Pass `--yes` to skip the prompt.

## How resumes work

There is no automatic resume — each batch run produces a fresh timestamped
directory. To "resume" after an interruption, use `--only` to re-run just
the scenarios that didn't complete:

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch `
    --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch `
    --only kitchen_matcha_morning_handheld_16 bathroom_marble_counter_flat_lay_20
```

The runner is fail-safe per scenario — exceptions in one scenario do not
abort the batch. Failed scenarios still appear in the overview with a red
"FAILED" badge, and Ctrl+C cleanly writes a partial overview.html with an
"(interrupted)" suffix in the title.

## Things this runner does NOT do

- It does not re-run Step 1 (PuLID). Persona scene image is always copied
  from the Plan A run as-is.
- It does not regenerate the OLD NB-shaped Step 2 prompt — that's copied
  verbatim from `04_step2_prompt.json` in the Plan A run.
- It does not regenerate the Qwen-v1 image — that's copied from the
  `--qwen-v1-root` if available, otherwise the v1 column shows "—".
- It does not modify any file outside `batch_runner/outputs/<timestamp>_batch/`.

## Shared cache

The runner inherits the parent experiment's shared `cache/fal_uploads.json` —
the product reference photo's fal URL is already cached from the previous
Qwen batch and will be reused. No re-uploads.

## Troubleshooting

**"missing system prompt: master_prompt_step2_qwen.md"** — you ran the script
from a directory where Python's path resolution can't find the experiment
folder. Run from the project root (`D:\video_automation_prototype\New_Image_flow`).

**"baseline reuse-run dir missing required files: [...]"** — the
`--plan-a-root` directory is missing one of the four required files for that
scenario. Re-run the corresponding Plan A scenario or supply a different
`--plan-a-root`.

**"--qwen-v1-root not found, will skip v1 column"** — the runner falls
back to A/B (NB vs Qwen-v2). Not an error, just a warning. Pass a valid
path if you want the full A/B/C.

**"Opus prompt regeneration failed"** — usually `ANTHROPIC_API_KEY` not set
in `.env`, or rate limited. Retry the failed scenarios with `--only`.

**"Qwen v2 FAILED"** — usually `FAL_KEY` not set, or transient fal API
issue, or content moderation flagged the prompt. The scenario will appear
in the overview with a red "FAILED" badge and can be retried with `--only`.