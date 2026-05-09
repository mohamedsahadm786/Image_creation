# Batch runner — FLUX-2-Klein-9B vs Nano Banana A/B comparison

Self-contained batch runner. Re-runs Step 2 with FLUX-2-Klein-9B Edit across **all scenarios** from an existing Plan A run, sequentially, and produces an HTML grid for direct A/B comparison.

## Why a separate folder

This folder is fully isolated from the parent `step2_flux2_klein_9b/` experiment:
- The parent's `run.py`, `trace_html.py`, etc. are **not modified**
- Single-run experiments (`python -m experiments.step2_flux2_klein_9b.run ...`) keep working exactly as before
- Batch outputs go to `batch_runner/outputs/`, not the parent's `outputs/`
- Same isolation pattern as the Qwen batch_runner — copy this folder, change two imports, done

## Usage

From the project root (`D:\video_automation_prototype\New_Image_flow`):

```powershell
# Run FLUX-2-Klein-9B against every scenario in a Plan A run (with confirmation prompt)
python -m experiments.step2_flux2_klein_9b.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a

# Skip the cost prompt (for scripted runs)
python -m experiments.step2_flux2_klein_9b.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --yes

# Restrict to specific scenarios
python -m experiments.step2_flux2_klein_9b.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --only outdoor_golden_hour_patio_27 pilates_mat_morning_handheld_09

# Skip specific scenarios
python -m experiments.step2_flux2_klein_9b.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --exclude bathroom_marble_counter_flat_lay_20

# Force regenerate Step 2 prompts via Opus (rarely needed)
python -m experiments.step2_flux2_klein_9b.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a `
    --rebuild-prompt
```

Before spending, the script prints scenario count and estimated cost, and asks for confirmation. For 30 scenarios at ~$0.025 each, expect ~$0.75 and **~3–5 minutes total** (much faster than Qwen's ~15 min — distilled 4-step inference makes per-call latency ~5–10s instead of ~30s).

## Output structure

Written to `experiments/step2_flux2_klein_9b/batch_runner/outputs/<timestamp>_batch/`:

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
│   ├── 05_step2_flux2_klein_final.jpg   (NEW — FLUX output)
│   ├── 05_step2_flux2_klein_meta.json   (NEW — timing, seed, request_id)
│   └── chain.html                       (4-panel A/B drill-down)
├── pilates_mat_morning_handheld_09/
│   └── ... (same structure)
└── ... (one subdir per scenario)
```

## How to read the A/B comparison

**Open `overview.html` first.** Each card in the grid shows two images side by side:

- **Left half labeled "NB"** — Nano Banana (existing baseline)
- **Right half labeled "FLUX"** — this experiment's output

Scroll the grid for at-a-glance scanning. When something interesting catches your eye (FLUX winning, losing, or doing something weird), **click the card** to open that scenario's `chain.html` for the full 4-panel drill-down: Step 0 reference → Step 1 PuLID → Step 2 Nano Banana → Step 2 FLUX-2-Klein-9B.

The chain.html also shows the prompt that was fed to both models (identical) and timing/seed metadata for each.

## Cross-experiment comparison

To compare FLUX results against the Qwen results from the previous experiment, just open both overview.html files in separate browser tabs:

- Qwen: `experiments/step2_qwen_edit_2511/batch_runner/outputs/<qwen_timestamp>_batch/overview.html`
- FLUX: `experiments/step2_flux2_klein_9b/batch_runner/outputs/<flux_timestamp>_batch/overview.html`

For each scenario, look at the same scenario_id in both grids. The Nano Banana column will be identical (it's the same baseline). The right-side column will show NB-vs-Qwen and NB-vs-FLUX respectively. If a scenario has Qwen ✓ / FLUX ✗ → Qwen wins it. Qwen ✗ / FLUX ✓ → FLUX wins it. Both ✓ / both ✗ — neither helps differentiate. Track these patterns across the 30 scenarios.

If we want a true 5-panel cross-experiment viewer (Step 0 / Step 1 / NB / Qwen / FLUX) we can build one as a separate top-level tool that ingests both batch outputs — but the side-by-side tab approach is enough for a first read.

## What to look for

| Check | Pass criterion |
|---|---|
| Face fidelity | FLUX face matches Nano Banana face and Step 1 (no drift) |
| Outfit | Same outfit, fabric, color |
| Scene | Same background, lighting direction |
| Product fidelity | Alluvi packaging text + colors + badges intact (no hallucination) |
| Product white base | White stays white, doesn't tint to scene color |
| Holding pose realism | Hand actually grips the box, not floating |
| Hand visibility | Both hands visible, no pockets |
| Scale | Box ~7 inches, not oversized |

## Why FLUX might behave differently than Qwen

- **Different reference image handling.** Qwen-Image-Edit-2511 is a unified MMDiT that fuses references via cross-attention; FLUX-2-Klein-9B uses a flow-matching architecture that treats edits as denoising trajectories. Same prompt, very different internal mechanics.
- **Different prompt sensitivity.** FLUX historically responds better to natural-language emphasis ("prominently featuring", "with particular attention to") than to weight syntax. Our master_prompt_step2.md is already model-agnostic per Section 9, but if FLUX is consistently weaker on prompt adherence, that's a known FLUX trait — would need prompt tuning per archetype.
- **Different distillation tradeoffs.** 4-step distilled models tend to be sharper on broad composition but lose fine detail (badge text, micro-textures). Watch for this on flat-lay scenarios specifically.

## Resume / interrupt behavior

If you Ctrl+C mid-batch, the script writes whatever it has accumulated:
- `batch_summary.json` is marked `"interrupted": true`
- `overview.html` renders with `(interrupted)` in the title and shows only the completed scenarios
- Partial scenarios where FLUX failed mid-call appear with FAIL status and an error message in their chain.html

Re-running the same command starts a fresh `<timestamp>_batch/` folder — no overlap with the interrupted run. There's no resume-from-where-you-left-off mode (yet); just rerun with `--exclude` to skip what already completed.