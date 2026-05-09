# flux_tuned_prompt / batch_runner

Two batch runners for the FLUX-tuned-prompt experiment:

| Runner | Mode | Cost (30 scenarios) | Wall time | When to use |
|---|---|---|---|---|
| `run_batch.py` | `--plan-a-root` (reuse) | ~$6 | ~15 min | A/B comparison vs Plan A NB baseline |
| `run_batch_full.py` | full from-scratch | ~$12 | ~25 min | All-fresh PuLID + FLUX, no Plan A needed |

Both reuse this experiment's `prompt_builder_flux.py` and `step_2_flux2_klein_edit.py` modules. They produce different overview HTMLs (2-up A/B grid vs single-card grid) and different per-scenario chain.htmls (4-panel vs 3-panel) — the `is_full_run` flag in the record dict tells `trace_html_batch.py` which layout to render.

---

## Mode 1 — `run_batch.py --plan-a-root` (A/B vs NB baseline)

**Pipeline per scenario:**
1. Validate Plan A baseline files exist
2. Opus 4.7 + master_prompt_step2_flux.md → FLUX-tuned Step 2 prompt + negative_prompt + fal_flux_params
3. Copy NB baseline image (for A/B comparison)
4. FLUX-2 Klein 9B Base Edit call with persona + assets/product.jpg
5. Per-scenario chain.html (4-panel: Step 0 / Step 1 / NB / FLUX)

**Pre-flight check** verifies:
- `assets/product.jpg` exists
- `master_prompt_step2_flux.md` exists
- `FAL_KEY` and `ANTHROPIC_API_KEY` set in environment

**Cost:**
- $0.15 — Step 2 prompt (Opus 4.7, ~250 words)
- $0.05 — FLUX-2 Klein 9B Base Edit
- **$0.20 per scenario** → ~$6.00 for 30 scenarios

**Usage:**

```powershell
# All 30 scenarios from a Plan A run
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a

# Single scenario
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --only bedroom_robe_with_product_13

# Skip difficulty=easy
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --exclude flat_lay_white_marble_29

# Skip cost confirmation
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch --plan-a-root outputs/runs/2026-05-08_17-04-15_plan_a --yes
```

---

## Mode 2 — `run_batch_full.py` (full from-scratch)

**Pipeline per scenario:**
1. Step 1 prompt — Opus 4.7 + project's `prompts/master_prompt_step1.md`
2. Stage 1 image — `fal-ai/flux-pulid` (PuLID) with `assets/persona.jpg`
3. Step 2 prompt — Opus 4.7 + this experiment's `master_prompt_step2_flux.md`
4. Stage 2 image — `fal-ai/flux-2/klein/9b/base/edit` with persona + `assets/product.jpg`
5. Per-scenario chain.html (3-panel: Step 0 / Step 1 / FLUX — no NB column)

**Pre-flight check** verifies:
- `assets/persona.jpg` exists
- `assets/product.jpg` exists
- `prompts/master_prompt_step1.md` exists
- `scenarios/scenarios.yaml` exists
- `master_prompt_step2_flux.md` exists
- `FAL_KEY` and `ANTHROPIC_API_KEY` set in environment

**Cost:**
- $0.10 — PuLID Stage 1 (fal API)
- $0.10 — Step 1 prompt (Opus)
- $0.15 — Step 2 prompt (Opus, FLUX-tuned)
- $0.05 — FLUX-2 Klein 9B Base Edit (fal API)
- **$0.40 per scenario** → ~$12.00 for 30 scenarios

**Usage:**

```powershell
# All 30 scenarios from scratch
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full

# Single scenario
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full --only bedroom_robe_with_product_13

# Skip cost confirmation
python -m experiments.step2_flux2_klein_9b.flux_tuned_prompt.batch_runner.run_batch_full --yes
```

---

## Output structure (both modes)

```
batch_runner/outputs/
└── <timestamp>_batch/    (--plan-a-root mode)         OR
└── <timestamp>_full/     (full from-scratch mode)
    ├── overview.html                    ← batch summary grid (orange accent)
    ├── batch_manifest.json              ← machine-readable summary + per-scenario records
    └── <scenario_id>/
        ├── chain.html                   ← per-scenario detail
        ├── 01_scenario.yaml
        ├── 02_step1_prompt.json
        ├── 03_step1_persona.jpg
        ├── 03_step1_meta.json           (only in --full mode — fresh PuLID meta)
        ├── 04_step2_nb_prompt.json      (only in --plan-a-root mode — for A/B prompt diff)
        ├── 04_step2_flux_prompt.json    ← FLUX-tuned prompt + negative_prompt + params
        ├── 05_step2_nb.jpg              (only in --plan-a-root mode)
        ├── 05_step2_nb_meta.json        (only in --plan-a-root mode)
        ├── 05_step2_flux.jpg            ← FLUX-2 Klein 9B Base Edit output
        └── 05_step2_flux_meta.json
```

---

## Output guarantees

Both runners are designed for batch reliability:

- **Per-scenario fail-safe:** any failure (Opus error, fal API timeout, network glitch) is caught at the scenario boundary; the rest of the batch continues
- **Mid-batch refresh:** `overview.html` and `batch_manifest.json` are rewritten every 5 scenarios so you can monitor progress live
- **Ctrl+C safe:** if you interrupt, partial outputs are written for completed scenarios with `interrupted: true` flag in summary
- **Pre-flight check** runs BEFORE any API call — missing inputs or env vars halt the run with a clear error message, not after spending Opus tokens

---

## Comparison HTML — what the overview shows

### `--plan-a-root` mode overview (`*_batch/overview.html`)

2-up grid: **NB baseline (left)** vs **FLUX-tuned (right, orange-bordered)**. Click any card for the full 4-panel chain.html with side-by-side prompt diff (NB-shaped vs FLUX-tuned) plus the negative_prompt displayed separately in red.

### `--full` mode overview (`*_full/overview.html`)

Single-card grid showing FLUX-tuned outputs only (no NB column since none was generated). Click for the 3-panel chain.html (Step 0 / Step 1 / FLUX).

Per-scenario meta pills in both modes show: category · archetype · difficulty · FLUX elapsed time · prompt word count · failure stage (if applicable).

---

## Comparing across experiments

Once you run both this FLUX experiment and the existing Qwen experiments, you can compare three Step 2 approaches side-by-side:

| Experiment | Endpoint | Color accent | Master prompt |
|---|---|---|---|
| qwen_tuned_prompt | qwen-image-edit-2511 | blue | original Qwen-tuned (with landscape language) |
| qwen_tuned_prompt_oriented | qwen-image-edit-2511 | purple | orientation-agnostic + picker layer |
| **flux_tuned_prompt (this)** | **flux-2/klein/9b/base/edit** | **orange** | **FLUX-tuned (180-260 words, negative_prompt)** |

Each experiment writes to its own `batch_runner/outputs/<timestamp>_full/` directory — no collisions, no overwrites. Run all three back-to-back to get a fair three-way comparison from the same scenarios.yaml.