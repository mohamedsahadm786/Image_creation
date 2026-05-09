# qwen_tuned_prompt_oriented experiment

Sibling to the `qwen_tuned_prompt/` experiment. Same Qwen model, same Step 2 master prompt structure — but adds a **hidden orientation-picker layer** between Step 2 prompt generation and the Qwen API call.

## Why this exists

Past Qwen runs failed in two specific ways when handling product orientation:

1. **Mirrored / redrawn product** when Qwen had to imagine how the design rotated to fit a vertical grip
2. **Pose conflicts** when the master prompt forced "natural landscape orientation, do not rotate to vertical" but the scenario's natural holding pose was vertical

Solution: pre-rotate the product image into 4 orientations and pick the right one at composition time. Qwen no longer has to reason about rotation — it just transfers a fixed appearance from a fixed-orientation reference.

## Architecture

```
   Step 2 prompt generation (Opus 4.7)
         ↓
   reads master_prompt_step2_qwen.md  ← knows nothing about rotation files
         ↓
   produces orientation-agnostic step_2_image_prompt
         ↓
   ┌──────────────────────────────────────────────┐
   │  HIDDEN LAYER — orientation picker           │
   │  Opus 4.7 + orientation_picker_prompt.md     │
   │  reads holding-pose sentence, returns one of:│
   │    horizontal | vertical | 45_right | 45_left│
   └──────────────────────────────────────────────┘
         ↓
   resolve assets/product_<orientation>.jpg
         ↓
   Qwen API call: image_urls = [persona, chosen_product]
   (Qwen sees a normal product photo — doesn't know it's pre-rotated)
```

The master prompt and the produced Step 2 prompt **never mention rotation**. They describe the holding pose. The picker reads the prompt and decides which orientation matches.

## Key files

| File | What |
|------|------|
| `master_prompt_step2_qwen.md` | The Step 2 system prompt — orientation-agnostic. Identical to your previous `qwen_tuned_prompt/master_prompt_step2_qwen.md` except for **one surgical change to Principle 9.a**: removed the "natural landscape orientation, do not rotate to vertical" lines (they conflict with the picker), added a new banned section forbidding any physical-orientation specifiers in the prompt. Everything else is preserved verbatim. |
| `orientation_picker_prompt.md` | NEW — small system prompt (~50 lines) for the picker Opus call. Describes the 4 orientations and selection rules (default horizontal, vertical for hip/forearm grips, 45° rarely). |
| `prompt_builder_qwen.py` | Has two functions: `build_step_2_prompt_qwen` (Step 2 prompt) and `pick_product_orientation` (picker). Each is a separate Opus call. |
| `step_2_qwen_edit_oriented.py` | Self-contained Qwen API caller that accepts `product_local_path` as a parameter. Does NOT modify the parent's `step_2_qwen_edit.py`. Reuses the shared `cache/fal_uploads.json`. |
| `config.yaml` | Standard config + `product_orientation_files` map + picker cost line. |
| `run.py` | Single-scenario CLI. |
| `trace_html.py` | 5-panel A/B/C chain.html with orientation badge + click-to-zoom lightbox. |
| `batch_runner/run_batch.py` | Batch CLI for the full 30 scenarios. |
| `batch_runner/trace_html_batch.py` | 3-up A/B/C overview grid + per-scenario chain.html with orientation badges. |

## Required asset files

Place these 4 pre-rotated product images at the project root (you've already done this):

```
assets/product_horizontal.jpg     # long side runs left-to-right (default)
assets/product_vertical.jpg       # long side runs top-to-bottom
assets/product_45_right.jpg       # rotated ~45° clockwise
assets/product_45_left.jpg        # rotated ~45° counter-clockwise
```

The runner verifies these exist before running and gives a clear error message if any is missing.

The original `assets/product.jpg` is left untouched and is no longer used by this experiment (the parent `qwen_tuned_prompt` experiment still uses it).

## Cost & timing

Per scenario:
- $0.18 — Step 2 prompt builder (Opus, ~8K input + ~800 output tokens)
- $0.02 — Orientation picker (Opus, ~600 input + ~80 output tokens)
- $0.04 — Qwen API call
- **$0.24 total per scenario** (was $0.22 in `qwen_tuned_prompt`; +$0.02 for the picker)

For 30 scenarios: **~$7.20 and ~17–18 minutes** sequential.

## Quick start

### Single-scenario test (~$0.24)

The robe scenario was a known failure case for the previous experiment — good test:

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.run --reuse-run outputs/runs/2026-05-08_17-04-15_plan_a/bedroom_robe_with_product_13 --reuse-qwen-v1 experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch/bedroom_robe_with_product_13
```

### Full 30-scenario batch (~$7.20)

```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch
```

See `batch_runner/README.md` for the full set of CLI options (--only, --exclude, --yes).

## Output layout

```
qwen_tuned_prompt_oriented/
└── outputs/<timestamp>_<scenario_id>/   (single-run)
or
└── batch_runner/outputs/<timestamp>_batch/<scenario_id>/   (batch)
    ├── chain.html                                ← A/B/C drill-down
    ├── 01_scenario.yaml                          (copied)
    ├── 02_step1_prompt.json                      (copied)
    ├── 03_step1_persona.jpg                      (copied)
    ├── 04_step2_nb_prompt.json                   (copied — OLD prompt for diff)
    ├── 04_step2_qwen_prompt.json                 (NEW — Qwen-tuned prompt)
    ├── 04b_orientation_picker.json               (NEW — picker decision + reasoning)
    ├── 05_step2_nb.jpg                           (copied — NB baseline)
    ├── 05_step2_nb_meta.json                     (copied)
    ├── 05_step2_qwen_v1.jpg                      (copied — Qwen with OLD prompt)
    ├── 05_step2_qwen_v1_meta.json                (copied)
    ├── 05_step2_qwen_v2.jpg                      (NEW — Qwen + new prompt + picked orientation)
    └── 05_step2_qwen_v2_meta.json                (NEW — includes picked_orientation field)
```

## What's new in the HTML viewer

- **Orientation badge** on the Qwen-v2 panel showing which orientation was picked (horizontal/vertical/45_right/45_left)
- **Picker reasoning banner** below the title showing why that orientation was chosen
- **Click-to-zoom** lightbox on every image panel
- **Side-by-side prompt diff** (OLD NB-shaped vs NEW Qwen-tuned + oriented)

## How the picker logic works

The picker reads Sentence 2 of the produced Step 2 prompt (the holding-pose sentence) and decides:

| Holding pose clue | Likely choice |
|---|---|
| "in front of body at chest level" / "front face toward camera" | horizontal |
| "at hip with arm relaxed down" / "carried at side" | vertical |
| "explicitly angled diagonally" / "wrist tilted right" | 45_right |
| "explicitly angled diagonally" / "wrist tilted left" | 45_left |
| Flat-lay / placed-on-surface | horizontal |
| Mirror selfie / held-with-phone | horizontal |
| Genuinely ambiguous | horizontal (default) |

Default bias is strongly toward `horizontal` — the picker only diverges from it when the holding pose clearly indicates otherwise. The 45° options are rare-use.

If the picker returns an invalid value (e.g. JSON parse error, weird LLM output), it falls back to `horizontal` and logs the issue.

## Things this experiment does NOT do

- Modify any file in `qwen_tuned_prompt/` or any other experiment folder
- Modify `prompts/`, `src/`, `pipelines/`, `assets/product.jpg`, or any other parent-level file
- Change the Qwen API parameters (same image_size, same num_images, same output_format)
- Change the persona / scenario / Step 1 PuLID call

Strictly additive. Sandboxed.