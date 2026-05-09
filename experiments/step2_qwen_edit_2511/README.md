# Experiment: Step 2 swap → fal-ai/qwen-image-edit-2511

## What this tests

Swaps **only the Step 2 model** (`fal-ai/nano-banana-2/edit` → `fal-ai/qwen-image-edit-2511`) and compares output side-by-side with the existing Plan A baseline.

Step 1 (PuLID), the Opus-generated Step 2 prompt, the persona image, the product image — **all unchanged**. This isolates the model swap as the only variable.

## Why Qwen-Image-Edit-2511

Verified against the **Image Edit Arena Leaderboard, February 2026** (arena.ai, blind human evaluation):

- **Highest-ranked truly open-weight image editor** with multi-image input
- **Apache 2.0 license** — commercial UGC ad use, no licensing concerns
- ELO 1239 (#14 globally), within striking distance of Nano Banana 2 at ELO 1313 (#7)
- November 2025 release explicitly targeted "industrial & product editing" and "identity preservation"
- Same `prompt + image_urls` API shape as Nano Banana — drop-in mechanical swap
- Self-hostable later when you move off fal entirely

## Prerequisites

- A completed Plan A scenario directory at `outputs/runs/<timestamp>_plan_a/<scenario_id>/` containing:
  - `01_scenario.yaml`
  - `02_step1_prompt.json`
  - `03_step1_persona.jpg`
  - `04_step2_prompt.json`
  - `05_step2_final.jpg` (baseline Nano Banana output, optional but recommended for side-by-side)
  - `05_step2_meta.json` (optional, used for cost/timing comparison)
- `FAL_KEY` in `.env` (already present per Plan A)
- `assets/product.jpg` (the same product reference Plan A uses)

## How to run

From the project root (`D:\video_automation_prototype\New_Image_flow`):

```powershell
# Default: reuse the exact Step 2 prompt that fed Nano Banana (recommended)
python -m experiments.step2_qwen_edit_2511.run `
    --reuse-run outputs/runs/<timestamp>_plan_a/outdoor_golden_hour_patio_27

# Optional: regenerate the Step 2 prompt via Opus first (rarely needed)
python -m experiments.step2_qwen_edit_2511.run `
    --reuse-run outputs/runs/<timestamp>_plan_a/outdoor_golden_hour_patio_27 `
    --rebuild-prompt
```

**Cost:** ~$0.04 (one Qwen Step 2 call). **Time:** ~20–60 seconds.

## Outputs

Written to `experiments/step2_qwen_edit_2511/outputs/<timestamp>_<scenario_id>/`:

```
01_scenario.yaml                  # copied from baseline run
02_step1_prompt.json              # copied
03_step1_persona.jpg              # copied
04_step2_prompt.json              # copied (same prompt for both models)
05_step2_nano_banana.jpg          # copied — baseline output
05_step2_nano_banana_meta.json    # copied if available
05_step2_qwen_final.jpg           # NEW — the Qwen output
05_step2_qwen_meta.json           # NEW — timing, seed, request_id, cost
chain.html                        # 4-panel side-by-side viewer
```

Open `chain.html` to see all four panels in order:

1. **Step 0** — Source `persona.jpg`
2. **Step 1 — PuLID** — Persona scene without product
3. **Step 2 — Nano Banana (baseline)** — Existing Plan A output
4. **Step 2 — Qwen (NEW)** — This experiment's output

…plus a metadata strip comparing endpoint, elapsed, cost, seed for both models, and the prompts used.

## How to interpret the comparison

Look for these specific failure / success modes when comparing panels 3 and 4:

| Check | Pass criterion |
|---|---|
| Face fidelity | Qwen panel shows the same face as Nano Banana panel and Step 1 (no drift) |
| Outfit fidelity | Same outfit, same fabric, same color |
| Scene fidelity | Same background, same lighting direction |
| Product fidelity | Alluvi packaging text + colors + badges match the product reference (no hallucination) |
| Product white base | White packaging stays white, doesn't tint to scene color (e.g. amber under golden hour) |
| Holding pose realism | Hand actually grips the box, not floating sticker-style |
| Hand visibility | Both hands visible, no pockets, no behind-back |
| Scale | Box ~7 inches wide relative to her hand — not oversized |

## Failure-handling decision tree

| Result | Next action |
|---|---|
| Qwen ≈ Nano Banana on the checks above | ✅ Switch primary to Qwen. Run the 6-scenario tier batch (Section 11 of handover). |
| Qwen face drifts but Nano Banana didn't | Try `--rebuild-prompt` to give Qwen a fresh Opus prompt; if still drifting, fall back to Backup 1 (FLUX 2 Klein 9B Edit). |
| Qwen mangles product packaging text | Expected weakness on certain prompts; try Backup 2 (Seedream 4.5 — closed weights but ELO 1316). |
| Qwen returns floating product | Same fix as the original NB debugging round 5 — the prompt is the issue, not the model. Fix on the main pipeline first. |
| Qwen call fails with API error | Read `05_step2_qwen_meta.json`. Most likely cause: wrong parameter name (Qwen has slightly different schema than NB). |

## Cloning this experiment for another model

This folder is the template. To test a different Step 2 model (e.g. FLUX 2 Klein 9B Edit, Seedream 4.5):

```powershell
# Copy the whole folder
Copy-Item -Path experiments/step2_qwen_edit_2511 `
          -Destination experiments/step2_<new_model_name> -Recurse
```

Then in the new folder:

1. **`config.yaml`** — change `experiment_name`, `model_label`, `step_2.endpoint`, and any model-specific parameters.
2. **`step_2_<model>.py`** — rename the file, update `FAL_ENDPOINT` constant, adjust which optional parameters get passed through. The function signature and return contract stay identical.
3. **`run.py`** — change the import from `step_2_qwen_edit` to `step_2_<model>`. Otherwise unchanged.
4. **`trace_html.py`** — update the panel label (`f"Step 2 — {model_label} (NEW)"` already renders dynamically via config, so usually no edit needed).
5. **`README.md`** — update the model name and rationale.

The orchestration logic (loading reuse-run, copying baseline files, building 4-panel chain.html, writing meta) is identical across all model experiments.

## Backup models for future experiments

Per the research (Image Edit Arena Feb 2026 rankings):

| Backup | fal endpoint | License | ELO | Why use it |
|---|---|---|---|---|
| FLUX 2 Klein 9B Edit | `fal-ai/flux-2/klein/9b/edit` | Apache 2.0 | 1232 | Tied with Qwen, different model family — different failure modes |
| Seedream 4.5 Edit | `fal-ai/bytedance/seedream/v4.5/edit` | Closed weights, commercial OK on fal | 1316 | Highest leaderboard rank — for scenarios where quality > openness |

## Known prompt builder note (out of scope, do not fix here)

`src/prompt_builder.py` contains a small contradiction: the user-message TASK section instructs Opus to use `"Image 1" / "Image 2"` reference syntax, while the system prompt (`master_prompt_step2.md`) explicitly bans that syntax as Nano Banana-specific (Section 9 of the handover). The system prompt's anti-examples should win and Opus should produce model-agnostic prompts, but this inconsistency is worth resolving in a separate follow-up. Not in scope for this experiment.