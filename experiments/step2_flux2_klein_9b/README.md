# step2_flux2_klein_9b — FLUX-2-Klein-9B Step 2 swap experiment

**Backup #1 (open source) per the locked recommendation order.** Tests `fal-ai/flux-2/klein/9b/edit` as a drop-in replacement for Nano Banana 2 in Step 2 product compositing.

## Why this model

From the Image Edit Arena Feb 2026 leaderboard:

| Model | License | ELO | Rank |
|---|---|---|---|
| Nano Banana 2 (Gemini 2.5 Flash Image) | Closed | 1313 | #7 |
| Qwen-Image-Edit-2511 | Apache 2.0 | 1239 | #14 |
| **FLUX-2-Klein-9B Edit** | **Apache 2.0** | **1232** | **#15** |

FLUX-2-Klein-9B is roughly tied with Qwen on the leaderboard but uses a **completely different architecture** (BFL rectified flow transformer vs Alibaba's MMDiT). The point of testing both is exactly that — failure modes differ. Qwen's mixed Plan A results showed neither model wins universally; if FLUX-2-Klein-9B wins on a different scenario subset (e.g. product-fidelity, hand-grip realism), we have a routing decision to make.

Why the **distilled 9B Edit** endpoint (`fal-ai/flux-2/klein/9b/edit`) and not the base 9B:
- fal officially recommends the distilled variant for production
- 4-step inference vs 28-step for base — sub-second per call
- Same quality ceiling on the leaderboard
- We're not training LoRAs in this experiment, so base-model flexibility is wasted here

## What it does

Re-runs **Step 2 only** against an existing Plan A baseline run. Reuses the same Step 1 PuLID image and the same Step 2 prompt — the prompt is the only variable held constant between Nano Banana, Qwen, and FLUX. True apples-to-apples.

Same isolation pattern as `step2_qwen_edit_2511/`:
- Nothing in the parent project gets modified
- Outputs go to this folder's own `outputs/` (single-run) or `batch_runner/outputs/` (batch)
- Uses the shared `cache/fal_uploads.json` for the product image (no redundant re-upload)

## Folder layout

```
step2_flux2_klein_9b/
├── __init__.py
├── README.md                     ← this file
├── config.yaml                   ← endpoint + parameters
├── step_2_flux2_klein.py         ← API caller (mirrors step_2_qwen_edit.py)
├── run.py                        ← single-run entry point
├── trace_html.py                 ← single-run 4-panel chain.html
├── outputs/                      ← single-run outputs land here (auto-created)
│
└── batch_runner/                 ← batch operations
    ├── __init__.py
    ├── README.md
    ├── run_batch.py              ← batch entry point (self-contained)
    ├── trace_html_batch.py       ← chain.html + overview.html grid
    └── outputs/                  ← batch outputs (auto-created)
```

## Usage

### Single scenario (debug / sanity check)

```powershell
cd D:\video_automation_prototype\New_Image_flow

python -m experiments.step2_flux2_klein_9b.run `
    --reuse-run outputs/runs/2026-05-08_17-04-15_plan_a/outdoor_golden_hour_patio_27
```

Cost: ~$0.025. Time: ~5–10s. Output: `experiments/step2_flux2_klein_9b/outputs/<timestamp>_<scenario_id>/chain.html`

### Full 30-scenario batch (the comparison test)

```powershell
python -m experiments.step2_flux2_klein_9b.batch_runner.run_batch `
    --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a
```

Cost: ~$0.75. Time: ~3–5 min (significantly faster than Qwen's ~15 min thanks to 4-step distilled inference). Output: `experiments/step2_flux2_klein_9b/batch_runner/outputs/<timestamp>_batch/overview.html`

See `batch_runner/README.md` for batch-specific options (`--only`, `--exclude`, `--yes`, `--rebuild-prompt`).

## Decision tree after this run

After you open the `overview.html` and visually scan the 30 NB-vs-FLUX A/B cards:

- **FLUX wins on different scenarios than Qwen wins.** This is the most interesting outcome — it means we should route per-scenario or per-archetype rather than picking one model. Build a 5-panel cross-experiment viewer (Step 0 / Step 1 / NB / Qwen / FLUX) to confirm, then decide on routing rules.
- **FLUX wins on the same scenarios Qwen lost.** Use FLUX for those archetypes (probably hand-grip / product-fidelity). Use NB for the rest until we fine-tune.
- **FLUX is universally worse than Qwen.** Drop it. Move to Backup #2 (Seedream 4.5, closed weights).
- **FLUX is universally better than Qwen.** Promote FLUX to primary; use it as the base model for Phase 3 fine-tuning instead of Qwen.

## What changed vs the Qwen experiment

If you've used `step2_qwen_edit_2511/`, this folder is a near-perfect clone with these surgical edits:

| File | Change |
|---|---|
| `config.yaml` | endpoint = `fal-ai/flux-2/klein/9b/edit`, model_label = "FLUX-2-Klein-9B", cost = $0.025 |
| `step_2_flux2_klein.py` | API caller renamed; `num_inference_steps` NOT passed (distilled fixes at 4) |
| `run.py` / batch_runner imports | `step_2_qwen_edit` → `step_2_flux2_klein`, dict key `step_2_qwen_meta` → `step_2_flux2_meta` |
| Output filenames | `05_step2_qwen_final.jpg` → `05_step2_flux2_klein_final.jpg` |
| HTML viewer accent color | Blue → amber (visual cue you're looking at the FLUX experiment, not Qwen) |

Everything else is identical.