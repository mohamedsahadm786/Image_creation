# Batch runner — Qwen-Image-Edit-2511 vs Nano Banana A/B comparison

Self-contained batch runner. Re-runs Step 2 with Qwen across **all scenarios** from an existing Plan A run, sequentially, and produces an HTML grid for direct A/B comparison.

## Why a separate folder

This folder is fully isolated from the parent `step2_qwen_edit_2511/` experiment:
- The parent's `run.py`, `trace_html.py`, etc. are **not modified**
- Single-run experiments (`python -m experiments.step2_qwen_edit_2511.run ...`) keep working exactly as before
- Batch outputs go to `batch_runner/outputs/`, not the parent's `outputs/`
- Same pattern can be replicated for batch experiments on other models — copy this folder, change two imports, done

## Usage

From the project root (`D:\video_automation_prototype\New_Image_flow`):

```powershell
# Run Qwen against every scenario in a Plan A run (with confirmation prompt)
python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a

# Skip the cost prompt (for scripted runs)
python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --yes

# Restrict to specific scenarios
python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --only outdoor_golden_hour_patio_27 pilates_mat_morning_handheld_09

# Skip specific scenarios
python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --exclude bathroom_marble_counter_flat_lay_20

# Force regenerate Step 2 prompts via Opus (rarely needed)
python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --rebuild-prompt
```

Before spending, the script prints scenario count and estimated cost, and asks for confirmation. For 30 scenarios at ~$0.04 each, expect ~$1.20 and ~15 minutes sequential.

## Output structure

Written to `experiments/step2_qwen_edit_2511/batch_runner/outputs/<timestamp>_batch/`:

```
<timestamp>_batch/
├── overview.html              ← OPEN THIS FIRST — A/B grid of all scenarios
├── batch_summary.json         ← totals: success/failed/cost/elapsed/timestamp
├── all_records.json           ← lightweight per-scenario records
├── outdoor_golden_hour_patio_27/
│   ├── 01_scenario.yaml                 (copied from baseline)
│   ├── 02_step1_prompt.json             (copied)
│   ├── 03_step1_persona.jpg             (copied)
│   ├── 04_step2_prompt.json             (same prompt for both models)
│   ├── 05_step2_nano_banana.jpg         (baseline output, copied)
│   ├── 05_step2_nano_banana_meta.json   (baseline meta, copied)
│   ├── 05_step2_qwen_final.jpg          (NEW — Qwen output)
│   ├── 05_step2_qwen_meta.json          (NEW — timing, seed, request_id)
│   └── chain.html                       (4-panel A/B drill-down)
├── pilates_mat_morning_handheld_09/
│   └── ... (same structure)
└── ... (one subdir per scenario)
```

## How to read the A/B comparison

**Open `overview.html` first.** Each card in the grid shows two images side by side:

- **Left half labeled "NB"** — Nano Banana (existing baseline)
- **Right half labeled "Qwen"** — this experiment's output

Scroll the grid for at-a-glance scanning. When something interesting catches your eye (Qwen winning, losing, or doing something weird), **click the card** to open that scenario's `chain.html` for the full 4-panel drill-down: Step 0 reference → Step 1 PuLID → Step 2 Nano Banana → Step 2 Qwen.

The chain.html also shows the prompt that was fed to both models (identical) and timing/seed metadata for each.

## What to look for

| Check | Pass criterion |
|---|---|
| Face fidelity | Qwen face matches Nano Banana face and Step 1 (no drift) |
| Outfit | Same outfit, fabric, color |
| Scene | Same background, lighting direction |
| Product fidelity | Alluvi packaging text + colors + badges intact (no hallucination) |
| Product white base | White stays white, doesn't tint to scene color |
| Holding pose realism | Hand actually grips the box, not floating |
| Hand visibility | Both hands visible, no pockets |
| Scale | Box ~7 inches, not oversized |

## Cloning this batch_runner for another model

If you create a new model experiment at `experiments/step2_<other_model>/`, copy this whole `batch_runner/` folder into it. Then in the copy:

1. **`run_batch.py`** — change two import lines:
   - `from experiments.step2_qwen_edit_2511 import step_2_qwen_edit` → `from experiments.step2_<other_model> import step_2_<other_model> as step_2_qwen_edit` (alias keeps the rest of the code unchanged), OR
   - rename the alias and update the one `step_2_qwen_edit.generate(...)` call site.

2. **`trace_html_batch.py`** — model label is read dynamically from config; no edit needed.

3. **`README.md`** — update model name and command paths.

Everything else (orchestration, cost confirmation, A/B grid, chain.html, summary writing) stays identical across model variants.

## Resume / interrupt behavior

If you Ctrl+C mid-batch, the script writes whatever it has accumulated:
- `batch_summary.json` is marked `"interrupted": true`
- `overview.html` renders with `(interrupted)` in the title and shows only the completed scenarios
- Partial scenarios where Qwen failed mid-call appear with FAIL status and an error message in their chain.html

Re-running the same command starts a fresh `<timestamp>_batch/` folder — no overlap with the interrupted run. There's no resume-from-where-you-left-off mode (yet); just rerun with `--exclude` to skip what already completed.