# flux_tuned_prompt experiment

Step 2 compositing experiment — uses **FLUX-2 Klein 9B Base Edit** with a FLUX-tuned master prompt. Sibling to the existing `step2_flux2_klein_9b/` (NB-shaped prompt) baseline.

## Why this exists

Past FLUX runs in this project used the model-agnostic Nano-Banana-shaped master prompt. That under-utilizes FLUX's strengths and triggers FLUX-specific failure modes:

1. **Verbose prompts hurt FLUX.** Per fal.ai's official Klein prompt guide: *"Overloaded prompts exceeding 100 words create confusion."* The NB-shaped prompt at 200+ words and the Qwen-tuned prompt at 400+ words both exceed FLUX's preferred density.
2. **No `negative_prompt` was used.** FLUX-2 Klein 9B Base Edit supports `negative_prompt` via classifier-free guidance — a major lever we left unused.
3. **No camera/lens specifications.** FLUX responds measurably better to specific photographic vocabulary ("Shot on 50mm at f/2.8") than generic "professional photo" language.
4. **No `guidance_scale` tuning.** Default 5.0 may be too loose for product photography; 6.0 gives stricter adherence.

This experiment re-tunes the prompt for FLUX's actual behavior and uses the **base** edit endpoint (not distilled) to unlock CFG/negative_prompt.

## Endpoint choice — Base, not Distilled

| Variant | Steps | negative_prompt | guidance_scale | Cost/img | When to use |
|---|---|---|---|---|---|
| `fal-ai/flux-2/klein/9b/edit` (distilled) | 4 | ❌ no CFG | ❌ fixed | ~$0.025 | speed |
| `fal-ai/flux-2/klein/9b/base/edit` (base) | 28 | ✅ yes | ✅ tunable | ~$0.05 | tunable quality ← **us** |

We use **`fal-ai/flux-2/klein/9b/base/edit`**. The distilled variant runs in 4 steps with fixed parameters — fast and cheap but gives us no levers to tune. The Base variant uses 28 inference steps with classifier-free guidance, which lets us pass `negative_prompt` and tune `guidance_scale`.

## FLUX-tuned prompt principles (how this differs from Qwen-tuned)

| Aspect | Qwen-tuned (other folder) | FLUX-tuned (this folder) |
|---|---|---|
| Word budget | 360–450 (HARD CEIL 480) | **180–260 (HARD CEIL 280)** |
| Identity anchors | Stacked "(keep X unchanged)" parentheticals | **ONE concise preservation clause** |
| Position re-anchoring | Positive + negative ("at chest level, not above her head, not at her hip") | Brief positive only |
| Anatomy clause | Verbose with occlusion handling | **Terse** ("Two arms, two hands, two legs, five fingers per hand") |
| Photorealism cues | Generic | **Camera/lens spec** (50mm at f/2.8, etc.) |
| `negative_prompt` | Not used (Qwen has no CFG) | **Required, focused on documented failure modes** |
| `guidance_scale` | N/A | **6.0** (slightly stricter than FLUX default 5.0) |
| Product orientation | Optional rotation files (oriented variant) | **Single product, anti-mirroring only** |

## Architecture

```
   Step 2 prompt generation (Opus 4.7)
         ↓
   reads master_prompt_step2_flux.md
         ↓
   produces:
     - step_2_image_prompt (180-260 words)
     - negative_prompt (focused on Alluvi failure modes)
     - fal_flux_params (guidance_scale 6.0, num_inference_steps 28, etc.)
         ↓
   FLUX-2 Klein 9B Base Edit
   image_urls = [persona, assets/product.jpg]
   prompt + negative_prompt + guidance_scale + steps
```

## Key files

| File | What |
|------|------|
| `master_prompt_step2_flux.md` | The FLUX-tuned system prompt — 9 operating principles, 8 anti-examples, 2 calibration examples. Ground truth for what's allowed and forbidden. |
| `prompt_builder_flux.py` | Drives Opus 4.7 with the master prompt to produce the Step 2 prompt envelope. |
| `step_2_flux2_klein_edit.py` | Self-contained FLUX 9B Base Edit caller. Does NOT modify parent or sibling experiment code. Reuses shared `cache/fal_uploads.json`. |
| `config.yaml` | Endpoint, costs, defaults (guidance_scale 6.0, num_inference_steps 28). |
| `run.py` | Single-scenario CLI (--reuse-run mode). |
| `trace_html.py` | 4-panel A/B chain.html with click-to-zoom + side-by-side prompt diff + negative_prompt display. |
| `batch_runner/run_batch.py` | Batch CLI (--plan-a-root mode, A/B comparison vs NB baseline across 30 scenarios). |
| `batch_runner/run_batch_full.py` | Full from-scratch CLI (PuLID Stage 1 + FLUX Stage 2 end-to-end, no Plan A reuse needed). |
| `batch_runner/trace_html_batch.py` | 2-up A/B overview grid + per-scenario chain.html. |

## Cost & timing

Per scenario:
- $0.15 — Step 2 prompt builder (Opus, ~7K input + ~500 output tokens; shorter than Qwen)
- $0.05 — FLUX-2 Klein 9B Base Edit (1MP input + 1MP output at ~$0.025/MP)
- **$0.20 total per scenario** (vs Qwen oriented at $0.24)

For 30 scenarios:
- A/B reuse mode (`run_batch.py`): **~$6.00**, ~15 min sequential
- Full from-scratch (`run_batch_full.py`): **~$0.20 + $0.10 PuLID + $0.10 Step 1 Opus = $0.40/scenario × 30 = ~$12.00**, ~30 min sequential

## Quick start

### Single-scenario test (~$0.20, ~30s)

```powershell
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.run --reuse-run outputs/runs/2026-05-08_17-04-15_plan_a/bedroom_robe_with_product_13
```

### Full 30-scenario A/B comparison vs NB baseline (~$6.00)

```powershell
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a
```

### Full from-scratch end-to-end (~$12.00)

```powershell
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full
```

## Output layout

```
flux_tuned_prompt/
└── outputs/<timestamp>_<scenario_id>/   (single-run)
or
└── batch_runner/outputs/<timestamp>_batch/<scenario_id>/   (--plan-a-root batch)
or
└── batch_runner/outputs/<timestamp>_full/<scenario_id>/   (full from-scratch batch)
    ├── chain.html                           ← 4-panel A/B with prompt diff
    ├── 01_scenario.yaml                     (copied)
    ├── 02_step1_prompt.json                 (copied or fresh in --full mode)
    ├── 03_step1_persona.jpg                 (copied or fresh in --full mode)
    ├── 04_step2_nb_prompt.json              (copied — for OLD/NEW prompt diff)
    ├── 04_step2_flux_prompt.json            (NEW — FLUX-tuned prompt + negative_prompt + params)
    ├── 05_step2_nb.jpg                      (copied — NB baseline)
    ├── 05_step2_flux.jpg                    (NEW — FLUX output)
    └── 05_step2_flux_meta.json              (NEW — seed, elapsed, cost)
```

## What's new in the HTML viewer

- **4-panel chain** (Step 0 / Step 1 / NB / FLUX) — orange accent on FLUX panel to distinguish from Qwen blue/purple
- **Click-to-zoom** lightbox on every image
- **Side-by-side prompt diff** showing both word counts
- **negative_prompt displayed separately** in red-tinted block
- **Compare strip** showing endpoint, guidance_scale, num_inference_steps, elapsed, seed per stage

## Things this experiment does NOT do

- Modify any file in the existing scaffolded `step2_flux2_klein_9b/` (parent folder)
- Modify any file in `experiments/step2_qwen_edit_2511/` or any other experiment
- Modify `prompts/`, `src/`, `pipelines/`, `assets/product.jpg`, or any other parent-level file
- Use the distilled FLUX endpoint (we use Base for tunable CFG)
- Use product orientation files / picker (single product only — explicitly excluded per user request)

Strictly additive. Sandboxed.