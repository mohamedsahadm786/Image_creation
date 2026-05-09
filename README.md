# Alluvi v2 — Image Generation Pipeline

UGC ad image generation for the Alluvi Tirzepatide 40mg peptide brand. Generates photoreal lifestyle images of a locked synthetic persona holding/showcasing the product across 30 hand-curated scenarios.

**Contain multiple flows. each of the flow have their own README.md file'. BTW, To run the final Flow, read the below content. That is the latest one**



---

## Quick Start

```powershell

# Create virtual environment
python -m venv venv


# Activate venv
.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Validate setup
python preflight.py


# Run all 30 scenarios
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch_full
```

Outputs go to `experiments\step2_qwen_edit_2511\qwen_tuned_prompt\batch_runner\outputs\/<timestamp>_full/`. Each scenario folder has a `chain.html` viewer showing Step 0 (source persona), Step 1 (PuLID scene), and Step 2 (final composite).

For comparison go to this directory - `experiments/step2_qwen_edit_2511/qwen_tuned_prompt/batch_runner/outputs/2026-05-09_20-07-27_full/overview.html`

---

**Another Flow is**

```powershell

# Run all 30 scenarios
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch_full
```

Outputs go to `experiments\step2_qwen_edit_2511\qwen_tuned_prompt_oriented\batch_runner\outputs\/<timestamp>_full/`. Each scenario folder has a `chain.html` viewer showing Step 0 (source persona), Step 1 (PuLID scene), and Step 2 (final composite).

For comparison go to this directory - `experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/batch_runner/outputs/2026-05-09_20-07-27_full/overview.html`

---

## Architecture

Two-step pipeline: **lock identity, free posture.**

| Step | Model | Cost | Job |
|---|---|---|---|
| 1 | `fal-ai/flux-pulid` | $0.04 | Generate persona + outfit + scene. NO product, NO empty-hand pre-posing. Both hands visible at natural resting positions. |
| 2 | `fal-ai/nano-banana-2/edit` | $0.04 | Composite the actual Alluvi product. Face/body/outfit/scene LOCKED. Holding arm/hand FREE to adjust naturally for grip. |

**Total cost:** ~$0.08 per image, ~$2.40 for all 30 scenarios.

Opus 4.7 (Anthropic) writes both prompts at runtime, reading from `prompts/master_prompt_step1.md` and `prompts/master_prompt_step2.md`.

---

## Setup

### Prerequisites

- Windows + PowerShell + Python 3.10
- Anthropic API key (Claude Opus 4.7)
- fal.ai API key

### Install

```powershell
git clone <repo>
cd New_Image_flow
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Configure

Create `.env` from `.env.example`:

```
ANTHROPIC_API_KEY=sk-ant-...
FAL_KEY=...
```

> **Important:** the variable name is `FAL_KEY`, not `FAL_API_KEY`.

### Verify

```powershell
python preflight.py
```

Should validate `assets/persona.yaml`, `scenarios/scenarios.yaml`, and report archetype distribution. No errors = ready.

---

## Project Structure

```
New_Image_flow/
├── .env                          API keys (not committed)
├── preflight.py                  Validates assets and scenarios before runs
├── requirements.txt
│
├── assets/
│   ├── persona.jpg               Full body persona reference
│   ├── persona_face_only.jpg     Face crop, used by Plan B
│   ├── product.jpg               Alluvi Tirzepatide box reference
│   ├── persona.yaml              Locked identity, prompt_descriptors block
│   └── product.yaml
│
├── brand/
│   ├── brand.yaml                Brand voice, palette, vibe tags
│   └── do_dont.md                Compliance rules
│
├── scenarios/
│   └── scenarios.yaml            30 hand-curated scenarios
│
├── prompts/
│   ├── master_prompt_step1.md    Opus system prompt for Step 1
│   └── master_prompt_step2.md    Opus system prompt for Step 2
│
├── src/
│   ├── db.py                     SQLite tracking
│   ├── scenario_loader.py        Archetype-aware validation
│   ├── prompt_builder.py         Opus 4.7 caller
│   ├── step_1_pulid.py           PuLID API caller
│   ├── step_1_kontext.py         Kontext API caller (Plan B, ready)
│   ├── step_1.py                 Plan-aware Step 1 dispatcher
│   ├── step_2_nano_banana.py     Nano Banana 2 Edit caller
│   ├── step_2.py                 Step 2 dispatcher
│   └── trace_html.py             chain.html viewer generator
│
├── pipelines/
│   ├── run_plan_a.py             Default: PuLID + Nano Banana
│   └── run_plan_b.py             Backup: Kontext + Nano Banana
│
├── config/
│   ├── default.yaml
│   ├── plan_a.yaml
│   └── plan_b.yaml
│
├── data/
│   └── alluvi.db                 SQLite (auto-created)
│
└── outputs/
    └── runs/
        └── {timestamp}_{plan}/
            ├── overview.html
            └── {scenario_id}/
                ├── 01_scenario.yaml
                ├── 02_step1_prompt.json
                ├── 03_step1_persona.jpg
                ├── 03_step1_meta.json
                ├── 04_step2_prompt.json
                ├── 05_step2_final.jpg     <- the final image
                ├── 05_step2_meta.json
                └── chain.html              <- visual review
```

---

## Daily Commands

```powershell
# Single scenario test (~$0.08)
python -m pipelines.run_plan_a --only outdoor_golden_hour_patio_27

# Multiple specific scenarios
python -m pipelines.run_plan_a --only pilates_reformer_mirror_06
python -m pipelines.run_plan_a --only bedroom_bed_handheld_close_11

# Full batch — all 30 scenarios (~$2.40)
python -m pipelines.run_plan_a

# Plan B (backup pipeline, Kontext-based Step 1)
python -m pipelines.run_plan_b --only outdoor_golden_hour_patio_27
```

---

## Reviewing Output

After any run, open the chain.html for visual review:

```powershell
start outputs\runs\{timestamp}_plan_a\{scenario_id}\chain.html
```

Three panels:
- **Step 0** — Source persona.jpg (the locked identity reference)
- **Step 1** — PuLID-generated persona scene with no product, hands at natural resting positions
- **Step 2** — Final composite with the product naturally held

For batch review, open `overview.html` in the run folder root — shows all scenarios as a grid.

---

## Quality Checklist (per scenario)

When reviewing chain.html, verify:

| ✅ | Check |
|---|---|
| ☐ | Step 1 face matches Step 0 persona.jpg (no identity drift) |
| ☐ | Step 1 outfit matches the scenario YAML, not persona.jpg's white sports bra |
| ☐ | Step 1 has both hands visible (no pockets, no hidden hands) |
| ☐ | Step 2 face matches Step 1 (no drift across compositing) |
| ☐ | Step 2 holding arm bent naturally, fingers actually grip the box |
| ☐ | Step 2 product is white (not amber-tinted by scene lighting) |
| ☐ | Step 2 product is realistic size relative to her hand (~7 inches wide) |
| ☐ | Step 2 product packaging text matches product.jpg (not mangled) |

---

## Configuration

### Key parameters (locked, in `config/plan_a.yaml`)

```yaml
step_1:
  defaults:
    image_size: { width: 768, height: 1344 }   # 9:16 for TikTok
    num_inference_steps: 30
    guidance_scale: 3.5    # lowered from 4.0 to reduce cartoonish look
    id_weight: 1.0         # FAL HARD CAP — values >1.0 = HTTP 422
    true_cfg: 1.5          # 1.7 for close-ups, 1.2 for full-body wide

step_2:
  defaults:
    aspect_ratio: "9:16"
    resolution: "1K"
    output_format: "png"
    safety_tolerance: "4"
```

### Why these values

`id_weight` is hard-capped at 1.0 by the fal API. Identity preservation comes from three combined sources:
1. The persona.jpg reference image (~50% weight)
2. The verbatim face descriptor in the prompt (~30% weight, amplified by true_cfg)
3. The identity_lock instruction at end of prompt (~20% weight)

For close-up framings, raise `true_cfg` to 1.7 — not `id_weight` (which can't go higher).

---

## Scenarios

30 hand-curated scenarios in `scenarios/scenarios.yaml`:

| Category | Count | Example |
|---|---|---|
| Gym | 5 | weights area cooldown, treadmill walk |
| Pilates | 5 | reformer, mat handheld |
| Bedroom | 4 | morning routine, bedside |
| Kitchen | 4 | matcha morning, counter prep |
| Bathroom | 3 | vanity, mirror routine |
| Recovery | 3 | couch evening, post-workout |
| Outdoor | 3 | patio golden hour, balcony |
| Hero flat-lay | 3 | marble studio, overhead |

**Difficulty:** 10 easy / 12 medium / 8 hard.

**Archetypes:**
- `held_product_high` — chest/face level
- `held_product_low` — hip/lap level
- `held_with_phone` — mirror selfies (one hand phone, one product)
- `placed_on_surface` — counter/bench placement
- `flat_lay` — pure product hero, no persona
- `object_in_lineup` — product among row of objects, no persona

---

## Troubleshooting

### `HTTP 422: id_weight must be ≤ 1`
You've exceeded fal's hard cap. Set `id_weight: 1.0` in config and master_prompt_step1.md. Use `true_cfg: 1.7` instead for stronger close-up identity.

### Step 1 face doesn't match persona.jpg
1. Check `prompts/master_prompt_step1.md` uses `face_descriptor_*` VERBATIM from `persona.yaml.prompt_descriptors`
2. For close-ups, ensure `true_cfg: 1.7` (not 1.5)
3. If still drifting, switch to Plan B (Kontext + face-only crop)

### Step 2 face changes from Step 1
The "lock identity" clause in master_prompt_step2.md isn't strong enough. Verify sentence 1 of the generated prompt explicitly locks face/hair/body/outfit. Check `outputs/.../04_step2_prompt.json`.

### Step 2 product is amber/orange instead of white
The white-base preservation clause is missing or weak. Verify Step 2 prompt includes: "Preserve the product's natural white packaging color — apply only the directional lighting and shadows of the scene, do not shift the product's base white to match the scene's color cast."

### Step 2 product floats / looks pasted-in
Step 1 was probably pre-posing an empty hand. Check `prompts/master_prompt_step1.md` enforces principle 6 (generate natural body, NOT pre-posed for product) and principle 8 (both hands visible at natural resting positions).

### Step 2 product is 20%+ too large
Verify Step 2 prompt includes the 7-inch scale anchor: "approximately 7 inches wide, sized realistically relative to her hand. Do not enlarge."

### chain.html shows "not generated" for Step 0
The persona.jpg path in `src/trace_html.py` should be `../../../../assets/persona.jpg` (4 levels up from scenario folder).

### Pipeline crashes mid-run on a failed scenario
`src/trace_html.py` should defensively handle `None` for `step_2_output` in `write_overview_html`. If you see `AttributeError: 'NoneType' object has no attribute 'get'`, the defensive None handling regressed.

---

## Roadmap

### Phase 1 — Plan A (CURRENT)
**Stack:** PuLID Step 1 + Nano Banana 2 Step 2.
**Status:** Architecture locked. Pilot batch validated. Scaling to 30-scenario runs.

### Phase 2 — Plan B (BACKUP, ready to deploy)
**Stack:** FLUX Kontext Step 1 + Nano Banana 2 Step 2.
**Trigger:** Switch if Plan A face fidelity falls below threshold across the tier batch.
**Tradeoff:** Kontext locks face better than PuLID at the API cap, but historically tries to preserve the reference's outfit (white sports bra). Mitigated by using `persona_face_only.jpg` (face crop, no outfit visible).

### Phase 3 — Open Source LoRA (PRODUCTION TARGET)
**Stack:** Self-hosted SDXL or FLUX.1-dev with custom LoRA fine-tuned on the persona.
**Goal:** Eliminate per-image API costs entirely. Deploy on dedicated GPU.
**When:** After Plan A or B locks acceptable quality at 30-image batch level.

**Critical for current development:** All prompts are written to be MODEL-AGNOSTIC. No "Image 1 / Image 2" syntax (Nano Banana-specific). No "compositing edit, NOT a regeneration" override (Nano Banana-specific). Generic "the persona reference photo" / "the product reference photo" so prompts transfer cleanly to the future LoRA.

---

## Compliance Rules

Hard bans (auto-fail at prompt build):

- No needles, syringes, injection imagery
- No competitor brands: Ozempic, Wegovy, Mounjaro, Zepbound
- No "weight loss", "shrinking", "fat loss", or specific pound figures
- No before/after framing
- No medical-coded imagery: doctors, lab coats, stethoscopes, prescription bottles
- Persona must read as 21+

All 30 scenarios are lifestyle UGC — never medical, never injection-coded.

See `brand/do_dont.md` for full list.

---

## Cost Reference

| Action | Cost |
|---|---|
| Single scenario test | $0.08 |
| 6-scenario tier batch | $0.48 |
| All 30 scenarios | $2.40 |
| 300/day production target | $24/day |

---

## Key Decisions (Locked)

These have been settled. Don't relitigate without strong reason.

- Outfit lives per-scenario, not in persona.yaml
- Persona descriptors used VERBATIM from persona.yaml — never paraphrase
- Step 1 generates a natural body with hands at resting positions, NOT pre-posed for a product
- Step 2 owns the holding pose entirely
- Both hands visible — no pockets, no hidden hands (hard rule)
- Product 7-inch scale anchor mandatory in Step 2
- Product white-base preservation mandatory in Step 2
- Step 2 prompts MUST be model-agnostic (no Nano Banana-specific syntax)
- id_weight=1.0 fixed (fal API hard cap)
- guidance_scale=3.5 (lowered from 4.0)
- Photoreal anchors REDUNDANT — both early (sentence 1) AND late (sentence 5)
- Sequential first, parallelism only after quality locks

---

## Need More Detail?

If onboarding a new collaborator (or a fresh AI chat), upload `alluvi_v2_handover.md` from the project root for the complete project history, debugging log, and decision rationale. This README is for operational reference; the handover doc is for context transfer.
