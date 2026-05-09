# Alluvi v2 Image Generation Pipeline — Project Briefing

**Document purpose.** This is a self-contained handoff document. Drop it into a new chat with the AI assistant and it will have full context — what we are building, what we have tested, what worked and what failed, where we currently stand, and what comes next. No need to re-explain anything from scratch.

**Last updated:** End of the prompt-tuning iteration cycle (Qwen-tuned prompt v4 = 578 lines, anatomy + occlusion + single-product clauses delivered).

---

## 1. Executive Summary

We are building an **automated TikTok ad image generation pipeline** for **Alluvi**, a UK premium Tirzepatide 40mg peptide brand. The end goal is **200 personas × 1 post/day = 200 unique TikTok ad images per day**, each featuring a Mediterranean female persona in a lifestyle scene, naturally interacting with the Alluvi product packaging.

The pipeline is a **two-stage compositing architecture** built around the principle of **"lock identity, free posture"**:

- **Stage 1** generates a clean persona-in-scene image with no product, both hands visible and unposed.
- **Stage 2** composites the actual Alluvi packaging into the persona's hand or onto a surface, with the holding arm freely adjusted for natural grip geometry.

Currently using `fal.ai` API for all model inference, with a strong preference for **open-source models** so we can self-host and fine-tune on the user's GPU server in Phase 3.

We are **mid-experiment**. The Stage 2 swap from Nano Banana 2 (closed) to Qwen-Image-Edit-2511 (open source) is producing usable but imperfect results after 4 iterations of prompt-tuning. The next planned experiment is a **Stage 1 model swap** to fix a slight cartoonic look in the source character image.

---

## 2. Project Context

### 2.1 Brand
- **Alluvi** — UK Tirzepatide 40mg peptide brand (premium positioning)
- Tirzepatide is a GLP-1/GIP dual agonist — same active ingredient as Mounjaro/Zepbound
- Product packaging: landscape-oriented white box (~2:1 wide:tall), TIRZEPATIDE / ALLUVI HEALTHCARE branding, blue molecular wave graphic, green "ALLUVI CERTIFIED" GMP seal, blue 40mg badge, transparent window showing an injection pen inside

### 2.2 Audience & aesthetic
- TikTok wellness/fitness audience, 2026 visual native language: **clean girl, pilates princess, gym girl, Alo-Yoga-coded, "that-girl"**
- Persona is a single Mediterranean female (face-locked across all 200 accounts variants will eventually rotate this)
- Scenarios: 30 hand-curated covering gym / pilates / bedroom / kitchen / bathroom / recovery / outdoor / flat-lay / hero shots

### 2.3 Compliance landmines
- TikTok Ads + Meta Ads have prohibited-products policies targeting weight-management
- One non-compliant ad can take down ad accounts, store accounts, and product listings
- Hard bans: needles being inserted into skin, before/after, weight scales, named competitors (Ozempic / Wegovy / Mounjaro / Zepbound), medical-professional impersonation, persona under estimated age 21
- Product packaging itself contains injection-related text — see Section 11.3 for how we resolved the tension between "no medical imagery" and "reproduce the product faithfully"

### 2.4 Cost target
- ~$0.08–0.22 per generated image at scale, depending on Stage 2 model + whether prompt regen is included
- Daily budget at 200 images/day = ~$16–44/day raw model cost

### 2.5 Working environment
- Project root: `D:\video_automation_prototype\New_Image_flow`
- OS: Windows, PowerShell
- Python venv: `.venv/`
- Environment variables in `.env`: `FAL_KEY`, `ANTHROPIC_API_KEY`
- LLM for prompt building: Claude **Opus 4.7** (`claude-opus-4-7`)

---

## 3. Pipeline Architecture

### 3.1 Two-stage compositing — why

A single-stage approach ("generate persona+product in one shot") has been tried and rejected because:
1. Identity drift is uncontrollable when the model has to lock face/hair/body AND faithfully render packaging AND generate scene AND figure out grip geometry simultaneously
2. Failure modes compound — a single bad output ruins everything
3. Compliance becomes harder to enforce when the model is asked to do too much at once

The two-stage approach decouples concerns:
- **Stage 1** = identity + scene (locked face, hair, body, outfit, environment, lighting) with no product
- **Stage 2** = product compositing (place actual packaging into Stage 1's image, adjust holding pose naturally)

This split is the **foundational design principle** of the project. Every experiment respects it.

### 3.2 ASCII diagram

```
┌────────────────────────┐         ┌──────────────────────────┐
│  persona.jpg           │         │  scenario.yaml           │
│  (face/identity ref)   │         │  (gym/bedroom/etc.)      │
└────────────┬───────────┘         └────────────┬─────────────┘
             │                                  │
             ▼                                  ▼
       ┌──────────────────────────────────────────────┐
       │  STAGE 1 — Character generation              │
       │  prompt: master_prompt_step1.md              │
       │  builder: src/prompt_builder.py (Opus 4.7)   │
       │  model: fal-ai/flux-pulid (currently)        │
       │  output: 03_step1_persona.jpg                │
       │    persona in scene, NO product, hands free  │
       └────────────────────────┬─────────────────────┘
                                │
                                ▼
       ┌──────────────────────────────────────────────┐
       │  03_step1_persona.jpg + assets/product.jpg   │
       └────────────────────────┬─────────────────────┘
                                │
                                ▼
       ┌──────────────────────────────────────────────┐
       │  STAGE 2 — Product compositing               │
       │  prompt: master_prompt_step2.md              │
       │            OR master_prompt_step2_qwen.md    │
       │  builder: src/prompt_builder.py (Opus 4.7)   │
       │            OR prompt_builder_qwen.py         │
       │  model:    fal-ai/nano-banana-2/edit         │
       │         OR fal-ai/qwen-image-edit-2511       │
       │         OR fal-ai/flux-2/klein/9b/edit       │
       │  output:   05_step2_final.jpg                │
       │    persona holding product, in scene         │
       └──────────────────────────────────────────────┘
```

### 3.3 Per-scenario file convention

Every scenario produces a numbered chain of files — same naming across all experiments for symmetry:

```
01_scenario.yaml          (the scenario brief, copied from scenarios/scenarios.yaml)
02_step1_prompt.json      (Step 1 prompt envelope from Opus, includes step_2_brief)
03_step1_persona.jpg      (Stage 1 model output — persona+scene, no product)
04_step2_prompt.json      (Step 2 prompt envelope from Opus)
05_step2_final.jpg        (Stage 2 model output — final image)
05_step2_meta.json        (Stage 2 generation metadata: seed, elapsed, cost, etc.)
chain.html                (visual A/B viewer for this scenario)
```

For experiments that have multiple Stage 2 candidates per scenario, additional files appear (e.g. `05_step2_qwen_v1.jpg`, `05_step2_qwen_v2.jpg`).

---

## 4. Stage 1 — Character Generation (currently PuLID)

### 4.1 Current model

- **Endpoint**: `fal-ai/flux-pulid`
- **Cost**: ~$0.10/image
- **Open source**: PuLID-FLUX is open source (https://github.com/ToTheBeginning/PuLID); same model on github as on the fal endpoint

### 4.2 Job specification

**Inputs**: `assets/persona.jpg` (face/identity reference) + Step 1 text prompt

**Output requirements**:
- Locked face, hair, skin tone, body proportions (must match `persona.jpg`)
- Outfit per scenario (verbatim from `scenarios.yaml`)
- Scene per scenario (gym, bedroom, kitchen, etc.)
- **Both hands visible**, unposed, hands not in pockets, not behind body, not cropped out
- No product anywhere
- 9:16 aspect ratio (TikTok native)

### 4.3 Status

**Identity preservation: ~99% accurate.** PuLID is excellent at locking facial features across scenes.

**Known issue: slight cartoonic / stylized rendering.** Skin sometimes reads as too smooth, slightly plastic, or lightly rendered rather than photorealistic. This propagates downstream — Stage 2 inherits the cartoonic look and may amplify it.

**Hand visibility is sometimes a partial failure.** In some scenarios (e.g. `bedroom_bed_handheld_close_11` lying-down archetype), the persona's hands end up below the frame edge or hidden, which makes Stage 2 much harder (Stage 2 has to materialize new hands AND place product, which compounds errors).

### 4.4 Prompt structure

`prompts/master_prompt_step1.md` (model-agnostic system prompt) drives Opus 4.7 to produce JSON envelopes containing:

- `step_1_image_prompt` (130–160 words, 200–250 acceptable for close-ups)
- `product_slot` (bridge data for Stage 2 — where product goes, what archetype, intended hand)
- `compliance_check` (boolean checklist)

`persona.yaml` `prompt_descriptors` are used **verbatim** — never paraphrased — to keep facial features consistent.

---

## 5. Stage 2 — Product Compositing (multiple models tested)

### 5.1 Models tested

| Plan | Endpoint | Cost/img | Open source? | Status |
|------|----------|----------|--------------|--------|
| **A (baseline)** | `fal-ai/nano-banana-2/edit` | $0.08 | ❌ Closed (Google Gemini) | ✅ 30 scenarios complete |
| **B-1 (open)** | `fal-ai/qwen-image-edit-2511` | $0.04 | ✅ Apache 2.0 | ✅ Multiple iterations complete |
| **B-2 (open)** | `fal-ai/flux-2/klein/9b/edit` | $0.025 | ✅ Apache 2.0 | ⏸️ Scaffolded, batch never run |
| **C (backup)** | `fal-ai/seedream-4.5` (or similar) | TBD | ❌ Closed | ⏸️ Not yet attempted |

### 5.2 Why open-source priority

The plan is to eventually **fine-tune** the Stage 2 model on Alluvi-specific compositions (Phase 3) and **self-host** on the user's 256GB GPU server. We prefer fal-available models that **also have open weights** because that path enables:

1. Today: Run experiments on fal API with no infra burden
2. Soon: Pick the best fal-available open-source model based on real Alluvi-specific data
3. Future: Fine-tune that same model on ~50–100 hand-curated production images via `fal-ai/qwen-image-edit-2511-trainer` (or equivalent)
4. Eventually: Deploy the fine-tuned model on self-hosted GPU for cost-controlled production at 200 images/day

This is why Nano Banana 2 (closed Gemini-based) is treated as a benchmark, **not a production target**. The production model needs to be open source.

### 5.3 Image Edit Arena (Feb 2026 leaderboard reference)

| Model | License | ELO | Rank |
|-------|---------|-----|------|
| Nano Banana 2 | closed | 1313 | #7 |
| Seedream 4.5 | closed | 1316 | #5 |
| **Qwen-Image-Edit-2511** | **Apache 2.0** | 1239 | #14 |
| **FLUX-2-Klein-9B Edit** | **Apache 2.0** | 1232 | #15 |

The two open-source candidates sit ~70–80 ELO points behind Nano Banana 2 — close enough that prompt-tuning + fine-tuning could close the gap for our specific use case.

---

## 6. Experiments Run So Far

### 6.1 Experiment 0 — Plan A baseline (PuLID + Nano Banana 2)

**Folder**: `outputs/runs/2026-05-08_17-04-15_plan_a/` (and other timestamped runs)

**Status**: 30 scenarios complete. Best fidelity overall — used as the gold-standard reference.

**Pipeline**:
- Stage 1: `fal-ai/flux-pulid`
- Stage 2: `fal-ai/nano-banana-2/edit` driven by `prompts/master_prompt_step2.md` (the model-agnostic master prompt)
- Total cost: ~$0.18/scenario (PuLID $0.10 + NB $0.08)
- Total batch: ~$5.40 for 30 scenarios

**Key takeaway**: Nano Banana 2 is the strongest packaging-fidelity baseline available. It rarely mirrors product, rarely produces anatomy artifacts, and renders small text legibly. But it's closed-source and cannot be fine-tuned. It exists as our quality ceiling reference.

---

### 6.2 Experiment 1 — Qwen-Image-Edit-2511 swap (NB-shaped prompt, no prompt tuning)

**Folder**: `experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch/`

**Pipeline change**: Same Stage 1 (PuLID), same Step 2 prompt (the model-agnostic `master_prompt_step2.md`, fed to both NB and Qwen), only Stage 2 model swapped to `fal-ai/qwen-image-edit-2511`.

**Status**: 30 scenarios complete. Mixed results — neither model dominates universally but Qwen had several documented failure modes.

**Failure modes observed in Qwen output** (vs the NB baseline):

1. **Mirrored product** — TIRZEPATIDE / ALLUVI text reading backwards. Qwen treated the product reference as a freely-orientable visual asset.
2. **Pose drift** — arm rotated to a completely different position than specified (e.g. straight up over head when prompt said face level).
3. **Identity-lock language softened** — face/hair/outfit/scene mostly survived but the holding pose was freely reinterpreted.
4. **Rare anatomy artifacts** — three arms, six or seven fingers per hand, fused fingers, missing fingertips. Low frequency (~1 in 15 outputs).

**Diagnosis**: Qwen-Image-Edit-2511 has a different architecture than Nano Banana — it uses a **dual encoder** (Qwen2.5-VL for semantic + VAE Encoder for appearance) rather than NB's unified Gemini transformer. It responds differently to prompts. The model-agnostic master prompt was written for NB and didn't address Qwen's specific sensitivities.

**Decision**: Don't reject Qwen — instead, write a Qwen-tuned master prompt that addresses the documented failure modes.

---

### 6.3 Experiment 2 — FLUX-2-Klein-9B swap (scaffolded only, batch never run)

**Folder**: `experiments/step2_flux2_klein_9b/`

**Status**: All code complete. Single-scenario test on `pilates_mat_morning_handheld_09` showed FLUX-2-Klein output was slightly worse than Qwen on the same prompt. Decision: pivot to Qwen prompt-tuning instead of running the full FLUX batch.

**Why FLUX is still on the roadmap**: Once the Stage 1 model selection is finalized (next big experiment) and we have a clean Qwen-tuned-prompt baseline, FLUX-2-Klein-9B will get the same prompt-tuning treatment for a fair comparison. It's the cheapest option ($0.025/img, distilled 4-step model) and may win on cost-per-quality after tuning.

---

### 6.4 Experiment 3 — Qwen + Qwen-tuned prompts (current focus)

**Folder**: `experiments/step2_qwen_edit_2511/qwen_tuned_prompt/`

**Pipeline change vs Experiment 1**: same Stage 1 (PuLID), same Stage 2 model (Qwen), but the **Step 2 prompt is regenerated by Opus 4.7 using a Qwen-tuned master prompt** (`master_prompt_step2_qwen.md`) instead of the model-agnostic master prompt.

**Architecture**:
```
Plan A scenario dir              previous Qwen batch dir          this experiment
─────────────────────            ────────────────────────         ─────────────────
01_scenario.yaml         ──┐     05_step2_qwen_final.jpg ──┐     04_step2_qwen_prompt.json   (NEW via Opus + qwen master prompt)
02_step1_prompt.json     ──┤                                │     05_step2_qwen_v2.jpg        (NEW via Qwen + new prompt)
03_step1_persona.jpg     ──┤                                │
05_step2_final.jpg       ──┴───► OPUS 4.7 ───────────────►  │     copies in: NB image as v_a
                                  (Qwen-tuned                │              Qwen-with-old-prompt as v1
                                   master prompt)            │              chain.html shows 5 panels
                                 QWEN ──────────────────────►│
```

**Per-scenario cost**: ~$0.22 = $0.18 Opus prompt regeneration + $0.04 Qwen API
**Per 30-batch**: ~$6.60 + ~17 minutes sequential

**HTML output**: 3-up A/B/C card grid (NB / Qwen-v1-old-prompt / Qwen-v2-new-prompt with purple border on v2). Each card clicks into a 5-panel chain.html showing Step 0 / Step 1 / NB / Qwen-v1 / Qwen-v2 plus the OLD/NEW prompt diff side-by-side.

#### 6.4.1 Iteration history of `master_prompt_step2_qwen.md`

| Version | Lines | What changed | Result |
|---------|-------|--------------|--------|
| **v1** (initial) | 565 | 9 principles: positional refs, identity locks with "keep X unchanged" anchors, posture freedom, hand visibility, product fidelity, lighting direction, scale anchor, word budget 280–380, anti-failure clauses (orientation lock, position re-anchoring, anatomy sanity) | Mostly improved on identity/pose/orientation; product packaging was still partially redrawn (text approximated, badges reorganized, layout drifted) |
| **v2** (FAILED) | 643 | Added "Principle 10 — Product pixel-fidelity" with three sub-clauses (pixel transfer mandate, box dimension lock, anti-redrawing clause). Word budget bumped to 360–480. New Anti-Example I added. | **Utter failure.** Bloated prompt reduced signal-to-noise. Output got *worse* than v1. User reverted to v1 baseline. Lesson: Qwen's encoder is sensitive to prompt density — too many redundant phrasings ("redraw / regenerate / redesign / reinterpret / paraphrase") hurt rather than help. |
| **v3** | 567 | Reverted to v1 baseline + extended Principle 9.a with one extra ~50-word clause covering **landscape orientation lock** ("the box is in its natural landscape orientation, ~2:1 wide:tall, do NOT rotate to vertical"). Both calibration examples updated. Word budget 320–410. | Significantly better. The "long side roughly vertical" bug in v1 was actively forcing Qwen to rotate the landscape box to portrait, causing the layout redesign. Removing that and adding explicit landscape orientation fixed product proportions. |
| **v4** (current) | 578 | Added to Principle 9.c (anatomy): explicit "two legs" + occlusion clause ("fingers and hands occluded by the product still fully exist — do not omit"). Added new Principle 9.d (single product / no duplicates) with mirror-reflection clarifier. Sentence 4 budget bumped slightly. Word budget 360–450. | Currently being tested. Fixes targeted: extra legs in lying-down poses, missing hands when occluded by product, multiple Alluvi boxes per frame. |

#### 6.4.2 What "v3 almost ok" looked like

- ✅ Character preservation: 100%
- ✅ Holding position: correct
- ✅ Product orientation: landscape, not mirrored
- ✅ Box proportions: matched real product
- ✅ Big text on packaging (TIRZEPATIDE, ALLUVI HEALTHCARE, 40mg badge): rendered
- ⚠️ Small fine-print text on packaging: still approximated (below Qwen's resolution threshold for legible text at 768×1344)
- ❌ Anatomy: occasional 3 hands, 6+ fingers, extra legs in lying-down scenes
- ❌ Sometimes 2 product copies per frame

v4 targets the last two issues.

---

## 7. Key Findings & Design Principles

### 7.1 Architecture: lock identity, free posture

**This is the foundational principle of the project.** A real person holding a real box has different arm geometry than a person with empty hands. Telling the Stage 2 compositor "preserve EVERYTHING in Image 1, just add product" produces sticker-like floating products. Telling it "lock face/hair/outfit/scene exactly + adjust arm/hand naturally to hold product" produces realistic compositions.

Identity-locked elements (must remain pixel-faithful to Stage 1):
- Face (every feature)
- Hair (color, length, styling)
- Body proportions
- Outfit
- Scene (background, surfaces, props)

Posture-free elements (may differ from Stage 1 to make holding natural):
- Holding arm angle and bend
- Holding hand grip and finger curl
- Slight body shift / weight redistribution
- Non-holding hand position

### 7.2 Qwen-specific prompt sensitivities (in master_prompt_step2_qwen.md)

These are documented in the master prompt itself, but summarized here for fast reference:

1. **Positional reference syntax required** — "the person from the first image" / "the product from the second image". Qwen's official guidance recommends this. **Opposite of Nano Banana**, which prefers generic "reference photo" language. The model-agnostic master prompt bans positional refs (correct for NB); the Qwen-tuned variant requires them.

2. **"Keep X unchanged" anchors threaded through Sentence 1** — Qwen's semantic encoder treats these as binding signals. Stack them parenthetically after each locked element: "her face (keep her face unchanged), her hair (keep her hair unchanged), her outfit (keep her outfit unchanged)..."

3. **Position re-anchoring with positive + negative coordinates** — "at chest level, not above her head, not at her hip, not beside her body". Without negative exclusions, Qwen drifts the holding position dramatically. Negative exclusions tailored per archetype.

4. **Orientation lock with landscape clause** — explicit anti-mirroring + the box stays in its natural landscape orientation, NOT rotated to vertical. Without this, Qwen redesigns the box layout into a portrait form factor.

5. **Anatomy sanity with occlusion handling** — exactly two arms, two hands, two legs, five fingers per hand. Fingers/hands hidden by the product still exist (Qwen sometimes "deletes" hands that would be partially behind the box; the rule names occlusion explicitly).

6. **Single product clause** — exactly ONE physical Alluvi product is visible, never duplicates. Mirror reflections count as the same product.

7. **White-base preservation** — apply the scene's lighting on top of white, do not tint white to match the scene's color cast (prevents amber-tinted product in golden-hour scenarios).

### 7.3 Things that did NOT work — DROPPED

- **Negative prompts.** Qwen wasn't trained with classifier-free guidance the way Stable Diffusion / Flux were. The `negative_prompt` parameter exists in the fal API but its effect is weak-to-nonexistent. PromptMaster blog ran a controlled grid experiment confirming this. **Do not waste prompt budget on negative_prompt for Qwen.**

- **Excessive prompt length.** Above ~480 words, signal-to-noise drops and Qwen's encoder gets diffuse. The v2 master prompt at 643 lines / ~500-word sentences proved this concretely.

- **Redundant anti-redraw language.** Phrases like "do not redraw, do not regenerate, do not redesign, do not reinterpret, do not paraphrase" stacked together produce no measurable improvement and actively hurt by diluting other clauses.

- **Banning all medical imagery in `do_dont.md`** when the product packaging itself contains injection-related text. This forced Qwen to render generic-looking white boxes (the safe direction). See Section 11.3 for how we resolved this.

### 7.4 Things that DID work

- **Cropping the product reference image** to remove lab-bench background. Qwen's VAE encoder was spending ~30–40% of its capacity on encoding microscope/glassware/blue counter, leaving less for the product itself. Replacing `assets/product.jpg` with a clean version (box only, white/transparent background) was a high-leverage easy fix.

- **Landscape orientation lock.** Once the master prompt stopped forcing Qwen to rotate the landscape box to vertical, the layout fidelity jumped substantially.

- **Positional role-tags + "keep X unchanged" anchors + position re-anchoring with negative exclusions** — the trio that fixed identity drift, pose drift, and orientation drift in v1.

- **"Almost cartoonic" hypothesis.** Currently believed: the cartoonic look originates partly in PuLID Stage 1 output and is amplified by Qwen Stage 2 smoothing. Stage 1 model swap is the next experiment to test this.

### 7.5 Honest expectation on Qwen-Image-Edit-2511 base model

Even with a fully-tuned master prompt, **Qwen base model will not match Nano Banana 2's pixel-perfect packaging fidelity.** That gap is architectural (different encoder design, different training data, smaller effective resolution for text rendering). The path to closing the gap is **fine-tuning** Qwen on Alluvi-specific compositions in Phase 3.

The current Qwen-tuned prompt gets us to roughly **70–80% of Nano Banana quality** at **half the cost** with **open-source weights**. That's the point of the project.

---

## 8. Current Folder Structure

```
D:\video_automation_prototype\New_Image_flow\
│
├── .env                                     # FAL_KEY + ANTHROPIC_API_KEY
├── .venv\                                   # Python virtual environment
│
├── assets\
│   ├── persona.jpg                          # Mediterranean female persona reference (face)
│   ├── persona.yaml                         # prompt_descriptors used VERBATIM
│   ├── product.jpg                          # Alluvi packaging (CROPPED CLEAN — no lab background)
│   └── product.yaml                         # Validation data (internal use only, never described in prompts)
│
├── brand\
│   ├── brand.yaml                           # Brand vibe + color palette
│   └── do_dont.md                           # UPDATED — see Section 11.3 (allows product packaging
│                                            # itself to contain injection imagery; bans persona
│                                            # PERFORMING injection only)
│
├── cache\
│   └── fal_uploads.json                     # Cached fal asset URLs (shared across all experiments
│                                            # — product upload reused, no re-uploads)
│
├── config\
│   ├── default.yaml
│   ├── plan_a.yaml                          # PuLID + Nano Banana 2
│   └── plan_b.yaml                          # PuLID + Plan B alt config
│
├── outputs\
│   └── runs\                                # Plan A runs — each timestamped subdir is one full
│       ├── 2026-05-08_17-04-15_plan_a\      #   30-scenario baseline run
│       ├── 2026-05-08_16-58-19_plan_a\
│       └── ...
│
├── pipelines\
│   ├── run_plan_a.py                        # Plan A end-to-end (PuLID + NB)
│   └── run_plan_b.py                        # Plan B alt end-to-end
│
├── prompts\
│   ├── master_prompt_step1.md               # Step 1 PuLID system prompt (model-agnostic)
│   └── master_prompt_step2.md               # Step 2 NB-shaped (model-agnostic) system prompt
│                                            # — this is the BASELINE master used for Plan A
│
├── scenarios\
│   └── scenarios.yaml                       # 30 hand-curated scenarios across:
│                                            #   gym (5) / pilates (3) / bedroom (4) / kitchen (4) /
│                                            #   bathroom (3) / outdoor (3) / hero (3) / flat-lay (3) /
│                                            #   plus other recovery/lifestyle scenarios
│
├── src\
│   ├── prompt_builder.py                    # Opus 4.7 caller — Step 1 + Step 2 prompts
│   ├── step_1_pulid.py                      # fal-ai/flux-pulid wrapper
│   ├── step_2_nano_banana.py                # fal-ai/nano-banana-2/edit wrapper
│   └── trace_html.py                        # Per-scenario chain.html generator (Plan A)
│
└── experiments\                             # Each experiment in its own sandboxed folder
                                             # NOTHING in src\ or pipelines\ is ever modified
    │
    ├── step2_qwen_edit_2511\                          # Experiment 1: Qwen swap, NB-shaped prompt
    │   ├── __init__.py
    │   ├── config.yaml                                # endpoint, cost, defaults
    │   ├── step_2_qwen_edit.py                        # fal-ai/qwen-image-edit-2511 wrapper
    │   │
    │   ├── batch_runner\
    │   │   ├── __init__.py
    │   │   ├── README.md
    │   │   ├── run_batch.py                           # CLI: --reuse-run-root --only --exclude --yes
    │   │   ├── trace_html_batch.py                    # 2-up grid (NB / Qwen)
    │   │   └── outputs\
    │   │       └── 2026-05-08_20-09-23_batch\         # 30 scenarios complete (Experiment 1)
    │   │
    │   └── qwen_tuned_prompt\                         # Experiment 3: Qwen + Qwen-tuned prompt
    │       ├── __init__.py
    │       ├── README.md
    │       ├── config.yaml                            # +cost_per_prompt_opus_usd: 0.18
    │       │                                          #  total per scenario: ~$0.22
    │       ├── master_prompt_step2_qwen.md            # ⭐ THE QWEN-TUNED MASTER (v4 = 578 lines)
    │       ├── prompt_builder_qwen.py                 # Opus caller using qwen master prompt
    │       ├── run.py                                 # Single-scenario CLI
    │       │                                          # --reuse-run + --reuse-qwen-v1
    │       ├── trace_html.py                          # 5-panel A/B/C chain.html
    │       │                                          #  (Step0 / Step1 / NB / Qwen-v1 / Qwen-v2)
    │       ├── outputs\                               # Single-run outputs (created on first run)
    │       │
    │       └── batch_runner\
    │           ├── __init__.py
    │           ├── README.md
    │           ├── run_batch.py                       # CLI: --plan-a-root --qwen-v1-root
    │           ├── trace_html_batch.py                # 3-up A/B/C grid + chain.html
    │           └── outputs\                           # Batch outputs (created on first batch)
    │
    └── step2_flux2_klein_9b\                          # Experiment 2: FLUX swap (scaffolded only)
        ├── __init__.py
        ├── README.md
        ├── config.yaml
        ├── run.py                                     # Single-scenario CLI
        ├── step_2_flux2_klein.py                      # fal-ai/flux-2/klein/9b/edit wrapper
        ├── trace_html.py                              # Single-run trace
        │
        └── batch_runner\
            ├── __init__.py
            ├── README.md
            ├── run_batch.py                           # CLI: --reuse-run-root --only --exclude --yes
            └── trace_html_batch.py                    # 2-up grid (NB / FLUX, amber theme)
```

### 8.1 Strict experiment isolation pattern

Every new experiment lives in **its own sandboxed folder**. Nothing in `src\`, `pipelines\`, `prompts\`, or any other parent-level folder is **ever modified**. This means:
- Multiple experiments can coexist
- Failed experiments cause no rollback
- Comparison across experiments is straightforward (each writes to its own outputs folder)
- The Plan A baseline is preserved permanently as a reference

When a new experiment is requested, the answer is **always**: create a new folder under `experiments\<descriptive_name>\` with its own config / runner / HTML viewer / outputs subdirectory. Never edit existing experiment files; never edit project-root code.

---

## 9. How Each Run Is Invoked

### 9.1 Plan A baseline (existing, do not modify)

```powershell
python -m pipelines.run_plan_a
```

Reads `config/plan_a.yaml`, generates 30 scenarios, writes to `outputs/runs/<timestamp>_plan_a/`.

### 9.2 Experiment 1 — Qwen with NB-shaped prompt (existing)

```powershell
python -m experiments.step2_qwen_edit_2511.batch_runner.run_batch --reuse-run-root outputs/runs/2026-05-08_17-04-15_plan_a
```

Reuses the Plan A run's Stage 1 outputs and Step 2 prompts; only re-runs Stage 2 with Qwen.

### 9.3 Experiment 3 — Qwen with Qwen-tuned prompt (current focus)

**Single-scenario test** (~$0.22, ~35s):
```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.run --reuse-run outputs/runs/2026-05-08_17-04-15_plan_a/bedroom_bed_handheld_close_11 --reuse-qwen-v1 experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch/bedroom_bed_handheld_close_11
```

**Full 30-batch** (~$6.60, ~17–18 min):
```powershell
python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --qwen-v1-root experiments/step2_qwen_edit_2511/batch_runner/outputs/2026-05-08_20-09-23_batch
```

⚠️ **PowerShell line continuation gotcha**: Use `` ` `` (backtick) at end of line with NO blank line after, OR write the command on a single line. Blank lines after backticks break the continuation.

### 9.4 Cost & time per experiment summary

| Experiment | Per-scenario | Per 30-batch | Wall time |
|------------|--------------|--------------|-----------|
| Plan A (PuLID + NB) | $0.18 | $5.40 | ~12 min |
| Experiment 1 (Qwen NB-prompt) | $0.04 | $1.20 | ~10 min |
| Experiment 3 (Qwen tuned-prompt) | $0.22 | $6.60 | ~17 min |
| Experiment 2 (FLUX, not yet run) | $0.025 | $0.75 | ~3–5 min |

---

## 10. HTML Trace Viewer System

Every experiment produces:

### 10.1 Per-scenario `chain.html`

A horizontal panel grid showing the full chain of images for one scenario. Variations:

- **Plan A**: 4-panel chain (Step 0 persona / Step 1 PuLID / Step 2 NB output / overlay info)
- **Experiment 1**: 4-panel chain (Step 0 / Step 1 / NB / Qwen)
- **Experiment 3**: 5-panel chain (Step 0 / Step 1 / NB / Qwen-v1-OLD-prompt / Qwen-v2-NEW-prompt) plus side-by-side OLD/NEW prompt diff
- All chains include scenario metadata, generation costs, elapsed times, seeds

### 10.2 Batch-level `overview.html`

A grid of cards, one per scenario, each with mini-thumbnails of the comparison images. Click any card → drill into that scenario's `chain.html`.

- **Experiment 1**: 2-up cards (NB-left / Qwen-right)
- **Experiment 3**: 3-up cards (NB / Qwen-v1 / Qwen-v2 with purple border on v2)

### 10.3 Current limitations (next-steps target — see Section 12.3)

- No image zoom — images are fixed thumbnail size, click only opens the chain.html
- Limited to 2-up or 3-up — as more experiments accumulate, we'll need 4-up / 5-up grids
- Prompt diff in chain.html is good but not perfectly side-by-side at very long widths
- No global search / filter by scenario archetype or by failure mode

---

## 11. Compliance Framework (do_dont.md)

### 11.1 Why it exists
- TikTok and Meta have prohibited-products policies targeting weight-management
- One non-compliant ad can take down accounts
- Auto-rejection gate before saving any output

### 11.2 Two-layer structure

**Layer 1 — Visual rules**: govern image generation (what's in the picture).
**Layer 2 — Caption / on-screen text rules**: govern any text overlays, captions, or voiceovers (governs ad copy, NOT image content).

Both layers go through Opus 4.7 prompt building, but Layer 2 doesn't currently affect image generation since we're not generating ad copy yet.

### 11.3 The needle/injection compromise (RESOLVED)

**Problem**: Original `do_dont.md` had a hard ban: "No needles, syringes, vials being injected, blood drops, IV bags, or any injection imagery — even abstract or partial." But the actual Alluvi product packaging label includes:
- "DUAL AGONIST OF GLP-1, GIP RECEPTORS"
- "For subcutaneous injection only"
- "Read package leaflet before use"
- A transparent window showing an injection pen inside the box

This created a tension. Qwen, asked to both reproduce the product faithfully AND avoid medical imagery, errs toward "render generic-looking white box without injection details" because that's the safe direction. Result: low-fidelity packaging.

**Resolution (current `brand/do_dont.md`)**: Distinguish between "the persona performing an injection" (still banned) and "the product packaging itself contains injection-related imagery" (now allowed).

Updated rule:
> *"DO NOT show the persona performing an injection — no needle being inserted into skin, no blood drop, no IV bag, no syringe held mid-air ready to inject. The product packaging itself is fine; the persona simply never uses the product visibly."*

The "Hard Compliance Rules" section was updated symmetrically. All caption/voiceover/text rules remain unchanged.

This unblocked Qwen — packaging fidelity improved measurably after this change because Qwen no longer suppresses parts of the product label.

### 11.4 What's still hard-banned in current `do_dont.md`

- Persona performing injection (needle into skin, blood, IV)
- Dramatic body reveals
- Alcohol, fast food, vapes, energy drinks
- Competitor brand logos / Apple Watch faces
- Doctors, lab coats, stethoscopes
- Persona looking ill / emaciated
- Multiple Alluvi products (covered now by Principle 9.d in master prompt)
- Before/after, weight scales, body measurements
- Named competitor drugs (Ozempic, Wegovy, Mounjaro, Zepbound)

---

## 12. Next Steps

### 12.1 Stage 1 model alternatives — IMMEDIATE PRIORITY

**Hypothesis**: The slight cartoonic look in final outputs originates partly in PuLID Stage 1. Stage 2 (Qwen) inherits and may amplify the stylization. Test by swapping Stage 1.

**Goal of Stage 1**: Preserve face / body color / hair / structure with **photorealistic skin texture**, while changing **outfit + scene** per scenario. PuLID nails the identity preservation (~99%) but produces somewhat smoothed/stylized skin.

**Test methodology** (3 phases):

#### Phase A — Reuse existing prompts
Take the existing Step 1 prompts already generated in Plan A runs (don't regenerate). Feed them to alternative Stage 1 models. If a model handles them well, no prompt-tuning is needed yet.

#### Phase B — Full-body persona reference
Use a **full-body** persona reference photo (face + body + costume) instead of just a face shot. Verify the candidate model:
- Preserves face identity
- Preserves body proportions
- **Allows costume to change per scenario** (the model should not lock costume)

#### Phase C — Face-only persona reference
If Phase B works, switch to a face-only persona reference. Verify:
- Identity still preserved
- Costume freely changes per scenario (since no costume in input)
- Body proportions still preserved (may need fallback to scenario.yaml)

**Candidate Stage 1 models to evaluate** (need to verify current fal availability):

| Model | Open source? | Strengths | Where to get |
|-------|--------------|-----------|--------------|
| **FLUX Kontext** | ❌ Closed | Strong photorealism, strong identity | fal-ai/flux-kontext |
| **OmniGen2** | ✅ Open | Multimodal, identity-aware | fal-ai (verify) or self-host |
| **InstantID** | ✅ Open | Strong face preservation | fal-ai/instant-id (verify) |
| **PhotoMaker v2** | ✅ Open | Tencent's identity model | fal-ai (verify) or self-host |
| **PuLID-FLUX with photorealism LoRA** | ✅ Open | Same model + style adjustment | self-host required |
| **Hunyuan ID** | ✅ Open | Strong likeness, photographic | self-host required |
| **ByteDance UNO / Phantom** | Partial | Identity + scene | fal-ai (verify) |
| **Higgsfield Soul** | ❌ Closed | Premium photorealism | fal-ai (verify) |

**Priority order for testing**:
1. **FLUX Kontext** — closed but premium quality; if it solves cartoonic look, gives us a quality ceiling reference (similar role to NB in Stage 2). Available on fal.
2. **OmniGen2** — best open-source candidate combining identity + photorealism.
3. **InstantID** — well-proven open-source identity preservation; widely deployed.
4. **PhotoMaker v2** — alternative open-source identity model.

**Folder structure for Stage 1 swap experiments** (proposed pattern):
```
experiments\
└── step1_<model_name>\
    ├── __init__.py
    ├── README.md
    ├── config.yaml
    ├── step_1_<model_name>.py            # API wrapper for the candidate model
    ├── run.py                             # Single-scenario, --reuse-prompt
    ├── trace_html.py                      # Stage-1-focused viewer
    └── batch_runner\
        ├── __init__.py
        ├── README.md
        ├── run_batch.py
        └── trace_html_batch.py            # Compare PuLID-Step1 vs new-Step1 vs final outputs
```

The HTML viewer for Stage 1 swap experiments should show:
- Source persona.jpg
- PuLID Step 1 output (existing baseline)
- Candidate model Step 1 output (NEW)
- Side-by-side comparison
- Same scenario brief used for both

If a Stage 2 result is needed for context, the existing Plan A `05_step2_final.jpg` can be copied in as a reference.

### 12.2 Stage 2 FLUX-tuned prompt (after Stage 1 selection)

Mirror the qwen_tuned_prompt approach for FLUX-2-Klein-9B:

1. Identify FLUX-2-Klein's specific prompt sensitivities (research)
2. Write `master_prompt_step2_flux.md` (analogous to qwen variant)
3. New experiment folder: `experiments/step2_flux2_klein_9b/flux_tuned_prompt/`
4. Same A/B/C HTML pattern: NB / FLUX-old-prompt / FLUX-new-prompt

This is **deferred** until Stage 1 selection is finalized — running FLUX-tuned-prompt on the wrong Stage 1 base would muddy the data.

### 12.3 HTML viewer enhancements

User-requested upgrades to the trace HTML system:

1. **Multi-way A/B/C/D... comparison.** Current is 2-up or 3-up; need 4-up and 5-up as more experiments accumulate. The grid layout should auto-flow based on the number of variants per scenario.

2. **Previous version + new version side-by-side per scenario.** When iterating a single experiment (e.g. qwen_tuned_prompt v3 → v4), the HTML should show:
   - The previous version's output image
   - The new version's output image
   - The previous version's prompt
   - The new version's prompt
   - Highlighted prompt diff

3. **Image zoom.** Click an image → modal/lightbox opens with full-resolution view. Currently images are fixed thumbnail size and you have to right-click → open image in new tab. A simple lightbox library (or hand-rolled `<dialog>` element) would do this cleanly.

4. **Scenario filter / archetype filter.** With 30 scenarios across 8 archetypes, filtering the overview grid by archetype (gym / pilates / bedroom / kitchen / ...) helps zero in on the failure mode being investigated.

5. **Failure-mode tagging.** Manual tags on each card (e.g. "mirrored", "anatomy", "redrawn") to track which scenarios fail in which ways across batches.

Not all of these need to land at once — prioritize zoom + multi-way grid first.

### 12.4 Phase 3 — Fine-tuning (long-term)

After Stage 1 + Stage 2 model selection is finalized:

1. Run the chosen pipeline across all 30 scenarios → produce ~30 high-quality outputs
2. Hand-curate / hand-edit ~50–100 production-quality images (combination of generated + manually adjusted)
3. Use these as fine-tuning data for the chosen open-source Stage 2 model
4. Train via `fal-ai/qwen-image-edit-2511-trainer` (or analogous endpoint for other model)
5. Deploy fine-tuned model on user's 256GB GPU server (config TBD — H200, multi-H100, or similar)
6. Production at 200 images/day routed to self-hosted endpoint

Cost projection for self-hosted: probably <$0.01/image after amortizing GPU costs over volume. Major savings vs API.

---

## 13. Decision Tree (Where to go next based on what happens)

### 13.1 Qwen-tuned prompt v4 results (current test)

| Outcome | Next move |
|---------|-----------|
| Anatomy + duplicate-product issues fixed, big text rendered | Run full 30-batch v4. Lock in this prompt as the production Qwen prompt. Move to Stage 1 swap experiments. |
| Anatomy fixed but duplicates persist | Iterate Principle 9.d wording. Add stronger explicit count language. |
| Duplicates fixed but anatomy persists | Iterate Principle 9.c with more explicit per-archetype anatomy clauses. |
| Big text still doesn't render | Increase Stage 2 output resolution from 768×1344 → 1024×1792. Verify Qwen-Image-Edit-2511 supports this on fal. |
| Cartoonic look persists across all outputs | Confirms hypothesis: Stage 1 model swap is needed. Skip further Qwen prompt-tuning, jump to Stage 1 experiments. |

### 13.2 Stage 1 model swap results

| Outcome | Next move |
|---------|-----------|
| Candidate model preserves identity AND looks photorealistic | Adopt as new Stage 1. Re-run Plan A baseline + all Qwen experiments with new Stage 1. |
| Candidate preserves identity but looks worse | Try next candidate; PuLID stays as Stage 1. |
| No candidate matches PuLID's identity preservation | Stay on PuLID. Investigate PuLID parameter tuning (`id_weight`, `num_inference_steps`, `guidance_scale`) to reduce stylization. Also try adding photographic language to the master_prompt_step1.md. |
| Best candidate is closed-source only | Use it as quality ceiling reference; continue evaluating open-source options for production. |

### 13.3 If absolutely nothing improves further

Phase 3 (fine-tuning) becomes the only remaining lever. We have enough baseline data after the existing experiments to start collecting fine-tuning corpus.

---

## 14. Reference Sheet

### 14.1 fal API endpoints used

```
fal-ai/flux-pulid                    # Stage 1 — current
fal-ai/nano-banana-2/edit            # Stage 2 — Plan A baseline
fal-ai/qwen-image-edit-2511          # Stage 2 — Backup 1 (open source)
fal-ai/flux-2/klein/9b/edit          # Stage 2 — Backup 1 alt (open source)
fal-ai/qwen-image-edit-2511-trainer  # Phase 3 — fine-tuning endpoint
```

### 14.2 Environment variables (.env)

```
FAL_KEY=<fal api key>
ANTHROPIC_API_KEY=<anthropic api key>
```

⚠️ Note: it's `FAL_KEY`, NOT `FAL_API_KEY`. This is a frequent source of "auth failed" errors.

### 14.3 LLM model

```
claude-opus-4-7
```

Used for both Step 1 prompt generation and Step 2 prompt generation. ~$0.18 per call on Step 2 with the Qwen-tuned master prompt.

### 14.4 Master prompt files (current)

```
prompts/master_prompt_step1.md                                            # Step 1 (model-agnostic)
prompts/master_prompt_step2.md                                            # Step 2 (NB-shaped, model-agnostic)
experiments/step2_qwen_edit_2511/qwen_tuned_prompt/master_prompt_step2_qwen.md
                                                                          # Step 2 (Qwen-tuned, v4 — 578 lines)
                                                                          # ⭐ THIS IS THE CURRENT FRONTIER
```

### 14.5 Static context files (loaded into every Opus call)

```
assets/persona.yaml              # prompt_descriptors used VERBATIM
assets/product.yaml              # validation only, NEVER described in prompts
brand/brand.yaml                 # vibe + palette
brand/do_dont.md                 # compliance (UPDATED — see Section 11.3)
```

### 14.6 Key data files

```
scenarios/scenarios.yaml         # 30 scenarios — DO NOT MODIFY (stable)
cache/fal_uploads.json           # Fal asset URL cache (shared across experiments)
```

### 14.7 Scenario IDs (the 30 scenarios)

```
gym_post_workout_mirror_01
gym_treadmill_water_break_02
gym_weights_area_cooldown_03
gym_locker_room_finish_04
gym_bag_open_lineup_05
pilates_reformer_mirror_06
pilates_post_class_floor_07
pilates_studio_handheld_08
pilates_mat_morning_handheld_09
pilates_post_workout_water_10
bedroom_bed_handheld_close_11
bedroom_vanity_getting_ready_12
bedroom_robe_with_product_13
bedroom_bedside_flat_lay_14
kitchen_supplements_lineup_15
kitchen_matcha_morning_handheld_16
kitchen_island_overhead_flat_lay_17
kitchen_coffee_bar_moment_18
bathroom_warm_oak_shelf_19
bathroom_marble_counter_flat_lay_20
bathroom_vanity_routine_21
recovery_foam_roller_22
recovery_post_workout_stretch_23
recovery_evening_wind_down_24
outdoor_post_walk_park_25
outdoor_smoothie_bar_26
outdoor_golden_hour_patio_27
hero_desk_styled_28
hero_marble_studio_29
hero_plant_botanical_30
```

(Some IDs may have minor variations; the canonical list is in `scenarios/scenarios.yaml`.)

### 14.8 Best-result reference scenarios (for spot-checking after any change)

When testing a master prompt change or model swap, run these first — they cover the failure-mode spectrum:

- `bedroom_bed_handheld_close_11` — close-up handheld (tests product fidelity at close range, anatomy in lying-down pose)
- `pilates_reformer_mirror_06` — held-with-phone mirror selfie (tests dual-image references, mirror reflection)
- `outdoor_golden_hour_patio_27` — held_product_high (tests white-base preservation under amber light)
- `kitchen_island_overhead_flat_lay_17` — flat lay (tests no-persona archetype, composition)
- `bathroom_marble_counter_flat_lay_20` — placed_on_surface (tests surface placement, hands-resting)

---

## 15. How to Resume Work in a New Chat

### 15.1 Briefing this assistant

1. Drop this PROJECT_BRIEFING.md into the new chat
2. Drop the current `master_prompt_step2_qwen.md` (current frontier file)
3. Drop the current `do_dont.md` (updated compliance file)
4. Optionally drop a recent Qwen output image showing the current state of failures (for diagnostic)
5. State the new task clearly

The assistant will have full context after that.

### 15.2 What the assistant must NOT do without explicit permission

- Modify any file in `src/`, `pipelines/`, `prompts/`, `config/`, `scenarios/`, `assets/`, `brand/`, or any existing experiment folder
- Create new files outside `experiments/<new_folder_name>/`
- Run any batch command without showing cost estimate first
- Reorganize the folder structure

### 15.3 What the assistant SHOULD do reflexively

- Strict experiment isolation — every new experiment in a new sandboxed folder
- Show cost estimates before any batch operation
- Use PowerShell-compatible single-line commands or backtick continuation with no blank lines
- Preserve every rule already in master prompts; never delete, only extend
- Read this briefing thoroughly before suggesting any change
- Research the specific model's documented sensitivities before writing a prompt for it

### 15.4 Communication style preferences

- Technical, decisive, concrete
- Surgical edits over rewrites
- Diagnose then fix; don't over-explain
- Stage tests carefully (single-scenario before batch)
- Show concrete commands, not abstract "you would run X"

---

## 16. Project Status Summary (as of this briefing)

| Component | Status | Notes |
|-----------|--------|-------|
| Plan A pipeline (PuLID + NB) | ✅ Production-ready | 30-scenario baseline complete |
| Experiment 1 (Qwen NB-prompt) | ✅ Complete | Mixed results; documented failure modes |
| Experiment 2 (FLUX) | ⏸️ Scaffolded | Code complete, batch deferred |
| Experiment 3 (Qwen tuned-prompt) | 🔄 v4 testing | 4 iterations; v3 was "almost ok"; v4 targets remaining anatomy/duplicate failures |
| Stage 1 model swap | ⏳ Next priority | Hypothesis: PuLID is source of cartoonic look |
| Stage 2 FLUX-tuned prompt | ⏳ Deferred | Until Stage 1 settled |
| HTML viewer enhancements | ⏳ Backlog | Zoom, multi-way grid, filters |
| Phase 3 fine-tuning | ⏳ Long-term | Needs ~50–100 hand-curated images first |
| Self-hosted GPU deployment | ⏳ Long-term | Hardware config TBD |

**Current frontier file**: `experiments/step2_qwen_edit_2511/qwen_tuned_prompt/master_prompt_step2_qwen.md` (v4, 578 lines).

**Current frontier task**: Test v4 master prompt; if anatomy + duplicate fixes hold, run full 30-batch and move to Stage 1 swap.

---

*End of briefing. This document is the single source of truth for project state through the v4 Qwen-tuned prompt iteration. When any major experiment milestone is reached, this document should be updated and re-saved.*
