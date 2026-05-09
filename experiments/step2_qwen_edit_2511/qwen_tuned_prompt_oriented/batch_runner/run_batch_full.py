"""
experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/batch_runner/run_batch_full.py

FULL FROM-SCRATCH batch runner for the qwen_tuned_prompt_oriented experiment.

Unlike run_batch.py (which reuses Stage 1 + NB outputs from a prior Plan A run),
this runner generates EVERYTHING from scratch for each scenario:

  1. Step 1 prompt — Opus 4.7 + project's prompts/master_prompt_step1.md
  2. Stage 1 image — fal-ai/flux-pulid using assets/persona.jpg + Step 1 prompt
  3. Step 2 prompt — Opus 4.7 + this experiment's master_prompt_step2_qwen.md
                     (orientation-agnostic)
  4. Orientation picker — Opus 4.7 + this experiment's orientation_picker_prompt.md
                          (returns horizontal | vertical | 45_right | 45_left)
  5. Resolve product file — assets/product_<orientation>.jpg
  6. Stage 2 image — fal-ai/qwen-image-edit-2511 with persona + chosen product

Per-scenario output:
  01_scenario.yaml
  02_step1_prompt.json          (NEW — fresh from Opus)
  03_step1_persona.jpg          (NEW — fresh from PuLID)
  03_step1_meta.json            (NEW — PuLID meta)
  04_step2_qwen_prompt.json     (NEW — fresh from Opus)
  04b_orientation_picker.json   (NEW — picker decision)
  05_step2_qwen_v2.jpg          (NEW — fresh from Qwen)
  05_step2_qwen_v2_meta.json
  chain.html                    (3-panel: Step 0 / Step 1 / Step 2)

Batch output:
  experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/batch_runner/outputs/<timestamp>_full/
    overview.html               (2-up cards: Step 1 + Qwen v2 with orientation pill)
    batch_manifest.json
    <scenario_id>/
      ...

Per-scenario cost (estimate):
  $0.10  PuLID Stage 1 (fal API)
  $0.10  Step 1 prompt (Opus)
  $0.18  Step 2 prompt (Opus)
  $0.02  Orientation picker (Opus)
  $0.04  Qwen Stage 2 (fal API)
  ─────
  $0.44  per scenario  → ~$13.20 for 30 scenarios

Wall time: ~70-90s per scenario sequential → ~35-45 min for 30 scenarios.

Usage (from project root D:\\video_automation_prototype\\New_Image_flow):

    python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch_full

    # or with filters:
    python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch_full --only bedroom_robe_with_product_13,outdoor_golden_hour_patio_27

    # or skip cost confirmation:
    python -m experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented.batch_runner.run_batch_full --yes
"""

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Project root: 4 levels up from
#   experiments/step2_qwen_edit_2511/qwen_tuned_prompt_oriented/batch_runner/run_batch_full.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# This experiment's modules
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented import prompt_builder_qwen
from experiments.step2_qwen_edit_2511.qwen_tuned_prompt_oriented import step_2_qwen_edit_oriented

# Lazy-loaded to give helpful errors if missing
import fal_client
import httpx
from anthropic import Anthropic


# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = EXPERIMENT_DIR / "config.yaml"
BATCH_OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"

STEP_1_MASTER_PROMPT = PROJECT_ROOT / "prompts" / "master_prompt_step1.md"

PERSONA_JPG = PROJECT_ROOT / "assets" / "persona.jpg"
PERSONA_YAML = PROJECT_ROOT / "assets" / "persona.yaml"
PRODUCT_YAML = PROJECT_ROOT / "assets" / "product.yaml"
BRAND_YAML = PROJECT_ROOT / "brand" / "brand.yaml"
DO_DONT_MD = PROJECT_ROOT / "brand" / "do_dont.md"
SCENARIOS_YAML = PROJECT_ROOT / "scenarios" / "scenarios.yaml"

CACHE_PATH = PROJECT_ROOT / "cache" / "fal_uploads.json"


# ──────────────────────────────────────────────────────────────────────────
# Constants & cost model
# ──────────────────────────────────────────────────────────────────────────

CLAUDE_MODEL = "claude-opus-4-7"
PULID_ENDPOINT = "fal-ai/flux-pulid"

EXPERIMENT_NAME = "step2_qwen_edit_2511_with_qwen_tuned_prompt_oriented_FROM_SCRATCH"

# Per-scenario cost components
COST_PULID_USD = 0.10
COST_OPUS_STEP1_USD = 0.10  # estimate; adjust if your Opus invoices differ
COST_OPUS_STEP2_USD = 0.18
COST_OPUS_PICKER_USD = 0.02
COST_QWEN_USD = 0.04
COST_PER_SCENARIO_USD = (
    COST_PULID_USD + COST_OPUS_STEP1_USD + COST_OPUS_STEP2_USD
    + COST_OPUS_PICKER_USD + COST_QWEN_USD
)

# Default PuLID params — override by adding `step_1.defaults` in config.yaml
DEFAULT_PULID_PARAMS = {
    "image_size": {"width": 768, "height": 1344},
    "num_inference_steps": 28,
    "guidance_scale": 4.0,
    "true_cfg": 1.0,
    "id_weight": 1.0,
    "max_sequence_length": 128,
    "num_images": 1,
    "output_format": "jpeg",
    "enable_safety_checker": True,
}


# ──────────────────────────────────────────────────────────────────────────
# Anthropic client (Step 1 prompt builder uses this)
# ──────────────────────────────────────────────────────────────────────────

_anthropic_client: Anthropic | None = None


def _get_anthropic_client() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment (.env)")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


# ──────────────────────────────────────────────────────────────────────────
# Step 1 prompt builder — self-contained
# ──────────────────────────────────────────────────────────────────────────

def build_step_1_prompt(scenario: dict) -> dict:
    """
    Build the Step 1 prompt envelope using the project's
    prompts/master_prompt_step1.md as the system prompt.

    This is a self-contained replica of what src/prompt_builder.py does
    for Step 1 — duplicated here so this experiment's runner has zero
    dependencies on src/ files. Reads but never modifies the project's
    master prompt.
    """
    if not STEP_1_MASTER_PROMPT.exists():
        raise FileNotFoundError(
            f"missing project Step 1 master prompt: {STEP_1_MASTER_PROMPT}"
        )

    paths_to_load = {
        "persona_yaml": PERSONA_YAML,
        "product_yaml": PRODUCT_YAML,
        "brand_yaml": BRAND_YAML,
        "do_dont_md": DO_DONT_MD,
    }
    missing = [p for p in paths_to_load.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing static context files (must run from project root):\n  "
            + "\n  ".join(str(p) for p in missing)
        )

    system_prompt = STEP_1_MASTER_PROMPT.read_text(encoding="utf-8")
    static_ctx = {k: p.read_text(encoding="utf-8") for k, p in paths_to_load.items()}

    user_message = "\n".join(
        [
            "=== persona.yaml (use prompt_descriptors VERBATIM — never paraphrase) ===",
            static_ctx["persona_yaml"],
            "",
            "=== product.yaml (INTERNAL VALIDATION ONLY — never describe in prompt) ===",
            static_ctx["product_yaml"],
            "",
            "=== brand.yaml ===",
            static_ctx["brand_yaml"],
            "",
            "=== do_dont.md (compliance) ===",
            static_ctx["do_dont_md"],
            "",
            "=== SCENARIO ===",
            json.dumps(scenario, indent=2),
            "",
            "=== TASK ===",
            "Build the Step 1 prompt envelope per the system prompt above.",
            "Output JSON only. No preamble. No markdown fences.",
        ]
    )

    print(f"[step_1_prompt] -> Opus 4.7 for scenario {scenario.get('id', '?')}")
    response = _get_anthropic_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return _parse_json(response.content[0].text)


# ──────────────────────────────────────────────────────────────────────────
# PuLID caller — self-contained
# ──────────────────────────────────────────────────────────────────────────

def _ensure_fal_key() -> None:
    if not os.getenv("FAL_KEY"):
        raise RuntimeError("FAL_KEY not set in environment (.env)")


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _upload_with_cache(local_path: str) -> str:
    _ensure_fal_key()
    abs_path = str(Path(local_path).resolve())
    cache = _load_cache()
    if abs_path in cache and isinstance(cache[abs_path], str):
        return cache[abs_path]
    print(f"[step_1_pulid] uploading: {abs_path}")
    url = fal_client.upload_file(abs_path)
    cache[abs_path] = url
    _save_cache(cache)
    return url


def run_pulid_step1(
    step_1_prompt_text: str,
    persona_local_path: str,
    fal_pulid_params: dict,
    out_path: Path,
    scenario_id: str,
) -> dict:
    """Run fal-ai/flux-pulid with persona reference + Step 1 prompt."""
    _ensure_fal_key()
    persona_url = _upload_with_cache(persona_local_path)

    arguments = {
        "prompt": step_1_prompt_text,
        "reference_image_url": persona_url,
        **fal_pulid_params,
    }

    print(f"[step_1_pulid] {scenario_id}: calling {PULID_ENDPOINT}")
    t0 = time.time()
    result = fal_client.subscribe(
        PULID_ENDPOINT, arguments=arguments, with_logs=False
    )
    elapsed = time.time() - t0

    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"PuLID returned no images for {scenario_id}: {result}")

    image_url = images[0].get("url")
    if not image_url:
        raise RuntimeError(f"PuLID image entry missing url for {scenario_id}: {images[0]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(image_url, timeout=180)
    response.raise_for_status()
    out_path.write_bytes(response.content)

    print(f"[step_1_pulid]   done in {elapsed:.1f}s, wrote {out_path}")

    return {
        "endpoint": PULID_ENDPOINT,
        "seed": result.get("seed"),
        "elapsed_seconds": round(elapsed, 1),
        "image_url": image_url,
        "persona_url": persona_url,
        "fal_pulid_params": fal_pulid_params,
    }


# ──────────────────────────────────────────────────────────────────────────
# Per-scenario orchestration
# ──────────────────────────────────────────────────────────────────────────

def process_scenario_full(
    scenario: dict,
    output_dir: Path,
    config: dict,
) -> dict:
    """Run the full from-scratch pipeline for one scenario. Never raises."""
    scenario_id = scenario.get("id", "?")
    output_dir.mkdir(parents=True, exist_ok=True)

    record: dict = {
        "scenario": scenario,
        "experiment": EXPERIMENT_NAME,
        "model_label": config.get("model_label", "PuLID + Qwen (oriented, from scratch)"),
        "output_dir": str(output_dir),
        "final_status": "pending",
    }

    # Save scenario yaml as 01_scenario.yaml for symmetry with Plan A output
    try:
        (output_dir / "01_scenario.yaml").write_text(
            yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8"
        )
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"failed writing 01_scenario.yaml: {e}"
        record["error_stage"] = "scenario_save"
        return record

    # ── 1. Step 1 prompt ──
    try:
        step_1_output = build_step_1_prompt(scenario)
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"Step 1 prompt build failed: {e}"
        record["error_stage"] = "step_1_prompt"
        return record

    step_1_text = (step_1_output or {}).get("step_1_image_prompt", "").strip()
    if not step_1_text:
        record["final_status"] = "failed"
        record["error_message"] = "step_1_image_prompt empty in Opus response"
        record["error_stage"] = "step_1_prompt"
        return record

    (output_dir / "02_step1_prompt.json").write_text(
        json.dumps(step_1_output, indent=2), encoding="utf-8"
    )
    record["step_1_output"] = step_1_output

    # ── 2. PuLID Stage 1 ──
    pulid_params = (
        config.get("step_1", {}).get("defaults", DEFAULT_PULID_PARAMS)
        or DEFAULT_PULID_PARAMS
    )
    persona_out_path = output_dir / "03_step1_persona.jpg"

    try:
        pulid_meta = run_pulid_step1(
            step_1_prompt_text=step_1_text,
            persona_local_path=str(PERSONA_JPG),
            fal_pulid_params=pulid_params,
            out_path=persona_out_path,
            scenario_id=scenario_id,
        )
        pulid_meta["cost_usd"] = COST_PULID_USD
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"PuLID Stage 1 failed: {e}"
        record["error_stage"] = "step_1_pulid"
        record["step_1_output"] = step_1_output
        return record

    (output_dir / "03_step1_meta.json").write_text(
        json.dumps(pulid_meta, indent=2), encoding="utf-8"
    )
    record["step_1_pulid_meta"] = pulid_meta

    # ── 3. Step 2 prompt (Qwen-tuned, orientation-agnostic) ──
    try:
        qwen_step_2_output = prompt_builder_qwen.build_step_2_prompt_qwen(
            scenario, step_1_output
        )
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"Step 2 prompt build failed: {e}"
        record["error_stage"] = "step_2_prompt"
        return record

    qwen_step_2_text = (qwen_step_2_output or {}).get("step_2_image_prompt", "").strip()
    if not qwen_step_2_text:
        record["final_status"] = "failed"
        record["error_message"] = "step_2_image_prompt empty in Opus response"
        record["error_stage"] = "step_2_prompt"
        record["step_2_qwen_prompt"] = qwen_step_2_output
        return record

    (output_dir / "04_step2_qwen_prompt.json").write_text(
        json.dumps(qwen_step_2_output, indent=2), encoding="utf-8"
    )
    record["step_2_qwen_prompt"] = qwen_step_2_output

    # ── 4. Orientation picker ──
    try:
        picker_result = prompt_builder_qwen.pick_product_orientation(
            qwen_step_2_text, scenario_id=scenario_id
        )
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"Orientation picker failed: {e}"
        record["error_stage"] = "orientation_picker"
        return record

    record["orientation_picker"] = picker_result
    (output_dir / "04b_orientation_picker.json").write_text(
        json.dumps(picker_result, indent=2), encoding="utf-8"
    )

    # ── 5. Resolve product file ──
    orientation = picker_result.get("orientation", "horizontal")
    orientation_map = config.get("product_orientation_files", {})
    product_rel = orientation_map.get(orientation)
    if not product_rel:
        record["final_status"] = "failed"
        record["error_message"] = (
            f"config.product_orientation_files has no entry for '{orientation}'"
        )
        record["error_stage"] = "product_resolution"
        return record

    product_path = (PROJECT_ROOT / product_rel).resolve()
    if not product_path.exists():
        record["final_status"] = "failed"
        record["error_message"] = f"product file missing: {product_path}"
        record["error_stage"] = "product_resolution"
        return record

    record["product_local_path"] = str(product_path)

    # ── 6. Qwen Stage 2 ──
    qwen_params = config.get("step_2", {}).get("defaults", {})
    qwen_out_path = output_dir / "05_step2_qwen_v2.jpg"

    try:
        qwen_meta = step_2_qwen_edit_oriented.generate_with_product(
            persona_local_path=str(persona_out_path),
            product_local_path=str(product_path),
            prompt=qwen_step_2_text,
            fal_qwen_params=qwen_params,
            out_path=qwen_out_path,
            scenario_id=scenario_id,
        )
        qwen_meta["picked_orientation"] = orientation
        qwen_meta["picked_orientation_reasoning"] = picker_result.get("reasoning", "")
        qwen_meta["cost_qwen_api_usd"] = COST_QWEN_USD
        qwen_meta["cost_pulid_api_usd"] = COST_PULID_USD
        qwen_meta["cost_opus_step1_usd"] = COST_OPUS_STEP1_USD
        qwen_meta["cost_opus_step2_usd"] = COST_OPUS_STEP2_USD
        qwen_meta["cost_opus_picker_usd"] = COST_OPUS_PICKER_USD
        qwen_meta["cost_total_usd"] = COST_PER_SCENARIO_USD
    except Exception as e:
        record["final_status"] = "failed"
        record["error_message"] = f"Qwen Stage 2 failed: {e}"
        record["error_stage"] = "step_2_qwen"
        return record

    (output_dir / "05_step2_qwen_v2_meta.json").write_text(
        json.dumps(qwen_meta, indent=2), encoding="utf-8"
    )
    record["step_2_qwen_v2_meta"] = qwen_meta
    record["final_status"] = "success"
    record["error_message"] = None

    # ── 7. Per-scenario chain.html ──
    try:
        write_chain_html_full(output_dir, record)
    except Exception as e:
        print(f"[scenario] {scenario_id}: chain.html write failed (non-fatal): {e}")

    return record


# ──────────────────────────────────────────────────────────────────────────
# Inline HTML viewers — 3-panel chain + 2-up overview
# ──────────────────────────────────────────────────────────────────────────

def write_chain_html_full(out_dir: Path, record: dict) -> None:
    """3-panel chain: Step 0 (persona ref) / Step 1 (PuLID) / Step 2 (Qwen v2)."""
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    final_status = record.get("final_status", "?")
    error_message = record.get("error_message")
    error_stage = record.get("error_stage")

    picker = record.get("orientation_picker") or {}
    picked_orientation = picker.get("orientation", "?")
    picker_reasoning = picker.get("reasoning", "")
    product_local_path = record.get("product_local_path", "?")

    # 7 levels up from {sid}/chain.html → project root → assets/persona.jpg
    persona_rel = "../../../../../../../assets/persona.jpg"

    if no_persona:
        step_0 = ("Step 0", "(no persona — flat-lay scenario)", None)
    else:
        step_0 = ("Step 0", "Source persona.jpg", persona_rel)

    panels = [
        step_0,
        ("Step 1 — PuLID (NEW)", "Persona scene (no product)", "03_step1_persona.jpg"),
        (f"Step 2 — Qwen v2 (orientation: {picked_orientation})",
         "Qwen with new prompt + picked orientation", "05_step2_qwen_v2.jpg"),
    ]

    cards = []
    for label, caption, src in panels:
        accent = "stage-new" if "Step 2" in label else ""
        if src is None:
            cards.append(
                f"""<div class="stage {accent}">
  <div class="stage-label">{html.escape(label)}<br><span class="stage-cap">{html.escape(caption)}</span></div>
  <div class="stage-empty">no persona in this scenario</div>
</div>"""
            )
        else:
            cards.append(
                f"""<div class="stage {accent}">
  <div class="stage-label">{html.escape(label)}<br><span class="stage-cap">{html.escape(caption)}</span></div>
  <img src="{html.escape(src)}" alt="{html.escape(caption)}"
       onerror="this.outerHTML='<div class=stage-empty>not produced</div>'">
</div>"""
            )

    step_1_prompt = (
        record.get("step_1_output", {}).get("step_1_image_prompt", "(not available)")
    )
    qwen_prompt = (
        record.get("step_2_qwen_prompt", {}).get("step_2_image_prompt", "(not available)")
    )
    step_1_wc = record.get("step_1_output", {}).get("word_count", "—")
    qwen_wc = record.get("step_2_qwen_prompt", {}).get("word_count", "—")

    pulid_meta = record.get("step_1_pulid_meta") or {}
    qwen_meta = record.get("step_2_qwen_v2_meta") or {}

    def _fmt_seconds(meta):
        s = meta.get("elapsed_seconds")
        return f"{s:.1f}s" if isinstance(s, (int, float)) else "—"

    def _fmt_seed(meta):
        s = meta.get("seed")
        return str(s) if s is not None else "—"

    badge = (
        '<span class="badge badge-ok">SUCCESS</span>'
        if final_status == "success"
        else '<span class="badge badge-fail">FAILED</span>'
    )

    error_block = ""
    if final_status != "success" and error_message:
        error_block = f"""<div class="error-block">
  <strong>Run failed at stage <code>{html.escape(str(error_stage or '?'))}</code>:</strong>
  {html.escape(str(error_message))}
</div>"""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(sc_id)} — Full from-scratch run</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937;max-width:1500px;margin:0 auto}}
  h1{{margin:0 0 6px 0;font-size:18px;padding:24px 24px 0}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:12px;padding:0 24px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .orient-banner{{background:#F5F3FF;border-left:3px solid #7C3AED;padding:10px 14px;
                 margin:0 24px 18px;border-radius:4px;font-size:13px;color:#5B21B6}}
  .orient-banner code{{background:#EDE9FE;padding:2px 6px;border-radius:3px;
                      font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:12px}}
  .stage-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;
             margin:0 24px 24px;padding:0}}
  .stage{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden}}
  .stage.stage-new{{border:2px solid #7C3AED;box-shadow:0 0 0 2px #EDE9FE}}
  .stage-label{{padding:10px 12px;border-bottom:1px solid #E5E7EB;font-size:12px;
               font-weight:600;background:#F9FAFB;line-height:1.4;min-height:50px}}
  .stage-new .stage-label{{background:#F5F3FF;color:#5B21B6}}
  .stage-cap{{font-weight:400;color:#6B7280;font-size:11px}}
  .stage img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#F3F4F6;
             cursor:zoom-in}}
  .stage-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;
               align-items:center;justify-content:center;color:#9CA3AF;font-size:11px;
               text-align:center;padding:0 8px}}
  .compare-strip{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;
                 padding:14px 18px;margin:0 24px 18px;font-size:13px;
                 display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  .compare-strip .col-title{{font-weight:600;margin-bottom:6px;font-size:12px;
                            text-transform:uppercase;letter-spacing:.5px;color:#374151}}
  .compare-strip .col.col-new .col-title{{color:#5B21B6}}
  .compare-strip .col-row{{color:#6B7280;font-size:12px;line-height:1.7}}
  .compare-strip .col-row strong{{color:#1F2937;font-weight:600}}
  .prompts{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:18px;
           margin:0 24px}}
  .prompts h3{{margin:0 0 8px;font-size:13px;color:#374151;text-transform:uppercase;
              letter-spacing:.5px}}
  .prompts h3.h3-new{{color:#5B21B6}}
  .prompt-block{{background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;
                padding:12px;font-size:12.5px;line-height:1.55;
                font-family:ui-monospace,'SF Mono',Menlo,monospace;
                margin-bottom:18px;white-space:pre-wrap;word-wrap:break-word}}
  .prompt-block.prompt-new{{background:#F5F3FF;border-color:#DDD6FE}}
  .prompt-meta{{font-size:11px;color:#6B7280;margin-bottom:4px;
               font-family:ui-monospace,'SF Mono',Menlo,monospace}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600;margin-left:6px}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
  .badge-experiment{{background:#EDE9FE;color:#5B21B6;margin-left:0;margin-right:6px}}
  .badge-orient{{background:#7C3AED;color:#fff;margin-left:0;font-size:11px}}
  .error-block{{background:#FFF7ED;border-left:3px solid #F97316;padding:10px 14px;
                margin:0 24px 18px;border-radius:4px;font-size:13px;color:#7C2D12}}
  .error-block code{{background:#FED7AA;padding:1px 6px;border-radius:3px}}
  .back{{display:inline-block;margin:24px 24px 0;color:#6B7280;font-size:12px;text-decoration:none}}
  .back:hover{{color:#1F2937;text-decoration:underline}}
  .lightbox{{display:none;position:fixed;top:0;left:0;width:100vw;height:100vh;
            background:rgba(0,0,0,.85);z-index:1000;cursor:zoom-out;
            align-items:center;justify-content:center}}
  .lightbox.active{{display:flex}}
  .lightbox img{{max-width:95vw;max-height:95vh;object-fit:contain}}
</style>
</head>
<body>
<a class="back" href="../overview.html">← Back to overview</a>
<h1>
  <span class="badge badge-experiment">FROM SCRATCH</span>
  {html.escape(sc_id)} — full pipeline {badge}
</h1>
<div class="meta">
  <span class="meta-pill"><strong>{html.escape(scenario.get('category', '?'))}</strong></span>
  <span class="meta-pill">{html.escape(scenario.get('archetype', '?'))}</span>
  <span class="meta-pill">{html.escape(scenario.get('difficulty', '?'))}</span>
</div>

<div class="orient-banner">
  <strong>Orientation picker:</strong> chose <code>{html.escape(picked_orientation)}</code> —
  {html.escape(picker_reasoning)}<br>
  <span style="font-size:11px;opacity:.7">product file used: {html.escape(product_local_path)}</span>
</div>

{error_block}

<div class="stage-row">
{''.join(cards)}
</div>

<div class="compare-strip">
  <div class="col">
    <div class="col-title">Step 1 — PuLID (fresh)</div>
    <div class="col-row">endpoint: <strong>fal-ai/flux-pulid</strong></div>
    <div class="col-row">prompt: <strong>{html.escape(str(step_1_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(pulid_meta)}</strong></div>
    <div class="col-row">seed: <strong>{_fmt_seed(pulid_meta)}</strong></div>
  </div>
  <div class="col col-new">
    <div class="col-title">Step 2 — Qwen v2 (oriented, fresh)</div>
    <div class="col-row">endpoint: <strong>fal-ai/qwen-image-edit-2511</strong></div>
    <div class="col-row">prompt: <strong>{html.escape(str(qwen_wc))} words</strong></div>
    <div class="col-row">orientation: <span class="badge badge-orient">{html.escape(picked_orientation)}</span></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(qwen_meta)}</strong></div>
    <div class="col-row">seed: <strong>{_fmt_seed(qwen_meta)}</strong></div>
  </div>
</div>

<div class="prompts">
  <h3>Step 1 prompt → fal-ai/flux-pulid</h3>
  <div class="prompt-meta">{html.escape(str(step_1_wc))} words</div>
  <div class="prompt-block">{html.escape(step_1_prompt)}</div>

  <h3 class="h3-new">Step 2 prompt → fal-ai/qwen-image-edit-2511 (orientation: {html.escape(picked_orientation)})</h3>
  <div class="prompt-meta">{html.escape(str(qwen_wc))} words</div>
  <div class="prompt-block prompt-new">{html.escape(qwen_prompt)}</div>
</div>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('active')">
  <img id="lightbox-img" src="" alt="">
</div>

<script>
  document.querySelectorAll('.stage img').forEach(img => {{
    img.addEventListener('click', () => {{
      const lb = document.getElementById('lightbox');
      const lbImg = document.getElementById('lightbox-img');
      lbImg.src = img.src;
      lb.classList.add('active');
    }});
  }});
</script>
</body>
</html>
"""
    (out_dir / "chain.html").write_text(html_doc, encoding="utf-8")


def write_overview_html_full(
    batch_dir: Path,
    records: list[dict],
    summary: dict,
) -> None:
    """2-up overview cards: Step 1 (left) + Qwen v2 (right with orientation pill)."""
    n = len(records)
    succeeded = summary.get("succeeded", 0)
    failed = summary.get("failed", 0)
    actual_cost = summary.get("actual_cost_usd", 0)
    elapsed = summary.get("elapsed_seconds", 0)
    timestamp = summary.get("timestamp", "?")
    interrupted = summary.get("interrupted", False)

    # Tally orientation distribution
    orientation_counts = {"horizontal": 0, "vertical": 0, "45_right": 0, "45_left": 0}
    failure_stages: dict[str, int] = {}
    for r in records:
        o = (r.get("orientation_picker") or {}).get("orientation")
        if o in orientation_counts:
            orientation_counts[o] += 1
        if r.get("final_status") != "success":
            stage = r.get("error_stage", "unknown")
            failure_stages[stage] = failure_stages.get(stage, 0) + 1

    cards = []
    for r in records:
        sc = r.get("scenario", {}) or {}
        sc_id = sc.get("id", "?")
        ok = r.get("final_status") == "success"
        badge_class = "badge-ok" if ok else "badge-fail"
        badge_text = "SUCCESS" if ok else "FAILED"

        picker = r.get("orientation_picker") or {}
        orient = picker.get("orientation", "?")

        step1_img = f"{sc_id}/03_step1_persona.jpg"
        v2_img = f"{sc_id}/05_step2_qwen_v2.jpg"
        chain_path = f"{sc_id}/chain.html"

        qwen_meta = r.get("step_2_qwen_v2_meta") or {}
        elapsed_s = qwen_meta.get("elapsed_seconds")
        elapsed_str = f"{elapsed_s:.1f}s" if isinstance(elapsed_s, (int, float)) else "—"

        qwen_wc = r.get("step_2_qwen_prompt", {}).get("word_count", "—")
        error_stage = r.get("error_stage", "")

        # Per-card error label if it failed
        error_pill = ""
        if not ok and error_stage:
            error_pill = f'<span class="meta-pill" style="background:#FEE2E2;color:#991B1B">failed: {html.escape(error_stage)}</span>'

        cards.append(
            f"""
<div class="card">
  <div class="card-header">
    <span class="card-id">{html.escape(sc_id)}</span>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <a href="{html.escape(chain_path)}" class="card-img-link">
    <div class="card-imgs">
      <div class="card-img-half">
        <div class="card-img-tag">Step 1 (PuLID)</div>
        <img src="{html.escape(step1_img)}" alt="step 1"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
      <div class="card-img-half card-img-new">
        <div class="card-img-tag tag-v2">Step 2 (Qwen)</div>
        <div class="card-orient-pill">{html.escape(orient)}</div>
        <img src="{html.escape(v2_img)}" alt="qwen v2"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
    </div>
  </a>
  <div class="card-meta">
    <span class="meta-pill">{html.escape(sc.get('category','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('archetype','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('difficulty','?'))}</span>
    <span class="meta-pill">qwen: {html.escape(elapsed_str)}</span>
    <span class="meta-pill">{html.escape(str(qwen_wc))}w prompt</span>
    {error_pill}
  </div>
</div>"""
        )

    title_suffix = " (interrupted)" if interrupted else ""

    orient_summary = " · ".join(
        f"<strong>{k}</strong>: {v}" for k, v in orientation_counts.items() if v > 0
    ) or "<em>no scenarios completed yet</em>"

    failure_summary = ""
    if failure_stages:
        failure_summary = (
            "Failures by stage: "
            + " · ".join(
                f"<strong>{html.escape(k)}</strong>: {v}"
                for k, v in sorted(failure_stages.items())
            )
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Full from-scratch batch — {html.escape(timestamp)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:0;background:#F4F6F8;color:#1F2937}}
  header{{background:#5B21B6;color:#fff;padding:24px 32px}}
  header h1{{margin:0 0 6px;font-size:22px;font-weight:600}}
  header .meta{{font-size:13px;opacity:.85;font-family:ui-monospace,'SF Mono',Menlo,monospace;line-height:1.7}}
  .summary-bar{{display:flex;gap:22px;padding:16px 32px;background:#fff;
               border-bottom:1px solid #E5E7EB;font-size:14px;flex-wrap:wrap}}
  .summary-bar .stat{{display:flex;gap:6px}}
  .summary-bar .stat-label{{color:#6B7280}}
  .summary-bar .stat-value{{font-weight:600}}
  .legend{{padding:10px 32px;background:#F9FAFB;border-bottom:1px solid #E5E7EB;
          font-size:12px;color:#6B7280}}
  .legend strong{{color:#1F2937}}
  .legend .v2-callout{{color:#5B21B6;font-weight:600}}
  .orient-summary{{padding:10px 32px;background:#F5F3FF;border-bottom:1px solid #DDD6FE;
                  font-size:12px;color:#5B21B6}}
  .failure-summary{{padding:10px 32px;background:#FFF7ED;border-bottom:1px solid #FED7AA;
                  font-size:12px;color:#7C2D12}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));
        gap:20px;padding:24px 32px}}
  .card{{background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;
        transition:box-shadow .15s ease}}
  .card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
  .card-header{{padding:10px 14px;border-bottom:1px solid #E5E7EB;
               display:flex;justify-content:space-between;align-items:center}}
  .card-id{{font-family:ui-monospace,monospace;font-size:11px;color:#6B7280}}
  .card-img-link{{display:block;text-decoration:none;color:inherit}}
  .card-imgs{{display:grid;grid-template-columns:1fr 1fr;gap:0}}
  .card-img-half{{position:relative;background:#F3F4F6}}
  .card-img-half.card-img-new{{box-shadow:inset 0 0 0 2px #7C3AED}}
  .card-img-half img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover}}
  .card-img-tag{{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.6);
                color:#fff;font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;
                z-index:2;letter-spacing:.5px}}
  .card-img-tag.tag-v2{{background:rgba(91,33,182,.95)}}
  .card-orient-pill{{position:absolute;top:6px;right:6px;background:#7C3AED;color:#fff;
                    font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;
                    z-index:2;letter-spacing:.3px}}
  .card-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;align-items:center;
              justify-content:center;color:#9CA3AF;font-size:12px}}
  .card-meta{{padding:8px 14px;border-top:1px solid #E5E7EB}}
  .meta-pill{{display:inline-block;background:#F3F4F6;padding:3px 9px;
             border-radius:4px;color:#4B5563;font-size:11px;margin-right:4px;margin-bottom:2px}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
</style>
</head>
<body>
<header>
  <h1>Full from-scratch run — Step 1 (PuLID) + Step 2 (Qwen + oriented){html.escape(title_suffix)}</h1>
  <div class="meta">
    {html.escape(timestamp)} · everything generated fresh from scenarios.yaml<br>
    no Plan A reuse, no Qwen-v1 comparison column
  </div>
</header>
<div class="summary-bar">
  <div class="stat"><span class="stat-label">Total:</span> <span class="stat-value">{n}</span></div>
  <div class="stat"><span class="stat-label">Success:</span> <span class="stat-value" style="color:#065F46">{succeeded}</span></div>
  <div class="stat"><span class="stat-label">Failed:</span> <span class="stat-value" style="color:#991B1B">{failed}</span></div>
  <div class="stat"><span class="stat-label">Cost:</span> <span class="stat-value">${actual_cost:.2f}</span></div>
  <div class="stat"><span class="stat-label">Elapsed:</span> <span class="stat-value">{elapsed:.0f}s ({elapsed/60:.1f} min)</span></div>
</div>
<div class="orient-summary">Orientation distribution: {orient_summary}</div>
{f'<div class="failure-summary">{failure_summary}</div>' if failure_summary else ''}
<div class="legend">
  Each card: <strong>Step 1 — PuLID (left)</strong> · <span class="v2-callout">Step 2 — Qwen v2 with picked orientation (right, purple)</span>. Click a card for the full 3-panel chain.html with prompt diff + click-to-zoom images.
</div>
<div class="grid">
{''.join(cards)}
</div>
</body>
</html>
"""
    (batch_dir / "overview.html").write_text(html_doc, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Discovery, filtering, and confirmation
# ──────────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing config: {CONFIG_PATH}")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_all_scenarios() -> list[dict]:
    if not SCENARIOS_YAML.exists():
        raise FileNotFoundError(f"missing scenarios file: {SCENARIOS_YAML}")
    data = yaml.safe_load(SCENARIOS_YAML.read_text(encoding="utf-8"))
    # scenarios.yaml is typically `{scenarios: [...]}` or just a list
    if isinstance(data, dict):
        scenarios = data.get("scenarios", []) or data.get("items", []) or []
    elif isinstance(data, list):
        scenarios = data
    else:
        scenarios = []
    if not scenarios:
        raise RuntimeError(f"no scenarios found in {SCENARIOS_YAML}")
    return [s for s in scenarios if isinstance(s, dict) and s.get("id")]


def _verify_inputs(config: dict) -> None:
    """Fail loudly BEFORE any API call if required files are missing."""
    problems = []

    if not PERSONA_JPG.exists():
        problems.append(f"missing persona reference: {PERSONA_JPG}")
    if not STEP_1_MASTER_PROMPT.exists():
        problems.append(f"missing Step 1 master prompt: {STEP_1_MASTER_PROMPT}")
    if not SCENARIOS_YAML.exists():
        problems.append(f"missing scenarios.yaml: {SCENARIOS_YAML}")

    orientation_map = config.get("product_orientation_files", {})
    if not orientation_map:
        problems.append("config.product_orientation_files is empty")
    for orient, rel in orientation_map.items():
        abs_path = (PROJECT_ROOT / rel).resolve()
        if not abs_path.exists():
            problems.append(f"missing product file ({orient}): {abs_path}")

    if not os.getenv("FAL_KEY"):
        problems.append("FAL_KEY not set in environment (.env)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY not set in environment (.env)")

    if problems:
        msg = "[batch_full] pre-flight check failed — run halted before any API calls:\n  " + "\n  ".join(problems)
        raise RuntimeError(msg)


def _filter_scenarios(
    scenarios: list[dict],
    only: list[str] | None,
    exclude: list[str] | None,
) -> list[dict]:
    if only:
        only_set = set(only)
        scenarios = [s for s in scenarios if s.get("id") in only_set]
    if exclude:
        excl_set = set(exclude)
        scenarios = [s for s in scenarios if s.get("id") not in excl_set]
    return scenarios


def _confirm_cost(n: int, yes: bool) -> bool:
    total = COST_PER_SCENARIO_USD * n
    # wall-time estimate: ~75s per scenario (PuLID 25s + Qwen 25s + 3 Opus calls ~25s)
    est_seconds = n * 75

    print("")
    print(f"[batch_full] scenarios:       {n}")
    print(f"[batch_full] per scenario:    ${COST_PER_SCENARIO_USD:.3f}")
    print(f"[batch_full]                    ${COST_PULID_USD:.3f}  PuLID Stage 1 (fal API)")
    print(f"[batch_full]                    ${COST_OPUS_STEP1_USD:.3f}  Step 1 prompt (Opus 4.7)")
    print(f"[batch_full]                    ${COST_OPUS_STEP2_USD:.3f}  Step 2 prompt (Opus 4.7)")
    print(f"[batch_full]                    ${COST_OPUS_PICKER_USD:.3f}  Orientation picker (Opus 4.7)")
    print(f"[batch_full]                    ${COST_QWEN_USD:.3f}  Qwen Stage 2 (fal API)")
    print(f"[batch_full] estimated cost:  ${total:.2f}")
    print(f"[batch_full] est. wall time:  ~{est_seconds // 60} min ({est_seconds}s sequential)")

    if yes:
        print("[batch_full] --yes flag set, skipping confirmation")
        return True

    answer = input("[batch_full] proceed? (y/n): ").strip().lower()
    return answer in ("y", "yes")


# ──────────────────────────────────────────────────────────────────────────
# Manifest writer (called periodically + at end)
# ──────────────────────────────────────────────────────────────────────────

def _write_manifest_and_overview(
    batch_dir: Path,
    records: list[dict],
    started_at: float,
    interrupted: bool,
) -> None:
    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    # Successful scenarios incurred full cost; failed scenarios incurred a partial cost
    # depending on which stage they failed at — be transparent and conservative
    actual_cost = 0.0
    for r in records:
        stage = r.get("error_stage")
        if r.get("final_status") == "success":
            actual_cost += COST_PER_SCENARIO_USD
        else:
            # partial spend depending on where it failed
            if stage == "scenario_save":
                actual_cost += 0.0
            elif stage == "step_1_prompt":
                actual_cost += COST_OPUS_STEP1_USD
            elif stage == "step_1_pulid":
                actual_cost += COST_OPUS_STEP1_USD + COST_PULID_USD
            elif stage == "step_2_prompt":
                actual_cost += COST_OPUS_STEP1_USD + COST_PULID_USD + COST_OPUS_STEP2_USD
            elif stage == "orientation_picker":
                actual_cost += (
                    COST_OPUS_STEP1_USD + COST_PULID_USD + COST_OPUS_STEP2_USD
                    + COST_OPUS_PICKER_USD
                )
            elif stage in ("product_resolution", "step_2_qwen"):
                actual_cost += (
                    COST_OPUS_STEP1_USD + COST_PULID_USD + COST_OPUS_STEP2_USD
                    + COST_OPUS_PICKER_USD
                )
                # Qwen partial? assume failed mid-call, half cost
                if stage == "step_2_qwen":
                    actual_cost += COST_QWEN_USD * 0.5
            else:
                actual_cost += COST_OPUS_STEP1_USD  # at minimum

    summary = {
        "succeeded": succeeded,
        "failed": failed,
        "actual_cost_usd": round(actual_cost, 3),
        "elapsed_seconds": time.time() - started_at,
        "timestamp": batch_dir.name,
        "interrupted": interrupted,
    }

    write_overview_html_full(batch_dir, records, summary)

    manifest = {
        **summary,
        "experiment": EXPERIMENT_NAME,
        "scenario_records": [
            {
                "scenario_id": r.get("scenario", {}).get("id", "?"),
                "final_status": r.get("final_status"),
                "error_stage": r.get("error_stage"),
                "error_message": r.get("error_message"),
                "picked_orientation": (r.get("orientation_picker") or {}).get(
                    "orientation"
                ),
                "picker_reasoning": (r.get("orientation_picker") or {}).get("reasoning"),
                "step_1_word_count": r.get("step_1_output", {}).get("word_count"),
                "step_2_qwen_word_count": r.get("step_2_qwen_prompt", {}).get(
                    "word_count"
                ),
                "step_1_seed": (r.get("step_1_pulid_meta") or {}).get("seed"),
                "step_2_qwen_seed": (r.get("step_2_qwen_v2_meta") or {}).get("seed"),
                "step_1_elapsed_s": (r.get("step_1_pulid_meta") or {}).get(
                    "elapsed_seconds"
                ),
                "step_2_qwen_elapsed_s": (r.get("step_2_qwen_v2_meta") or {}).get(
                    "elapsed_seconds"
                ),
            }
            for r in records
        ],
    }
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Full from-scratch batch runner for the qwen_tuned_prompt_oriented "
            "experiment. Generates Step 1 (PuLID) + Step 2 (Qwen + oriented) "
            "for every scenario in scenarios.yaml. No Plan A reuse."
        )
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="comma-separated scenario IDs to include (default: all)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        help="comma-separated scenario IDs to skip",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip cost confirmation prompt",
    )
    args = parser.parse_args()

    config = _load_config()

    # Pre-flight check — fail loudly before any spend if anything is missing.
    try:
        _verify_inputs(config)
    except RuntimeError as e:
        print(str(e))
        return 1

    # Discover and filter scenarios
    try:
        all_scenarios = _load_all_scenarios()
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[batch_full] {e}")
        return 1

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    exclude = [s.strip() for s in args.exclude.split(",")] if args.exclude else None
    scenarios = _filter_scenarios(all_scenarios, only, exclude)

    if not scenarios:
        print(f"[batch_full] no scenarios to run after filtering ({len(all_scenarios)} available)")
        if only:
            print(f"[batch_full]   --only filter: {only}")
        if exclude:
            print(f"[batch_full]   --exclude filter: {exclude}")
        return 1

    if not _confirm_cost(len(scenarios), args.yes):
        print("[batch_full] aborted by user")
        return 0

    # Output dir
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    batch_dir = BATCH_OUTPUT_ROOT / f"{timestamp}_full"
    batch_dir.mkdir(parents=True, exist_ok=True)

    print("")
    print(f"[batch_full] output dir:       {batch_dir}")
    print(f"[batch_full] scenarios queued: {len(scenarios)}")
    print("")

    records: list[dict] = []
    started_at = time.time()
    interrupted = False

    try:
        for i, scenario in enumerate(scenarios, start=1):
            sc_id = scenario.get("id", f"unknown_{i}")
            scenario_started = time.time()
            print(
                f"[batch_full] [{i}/{len(scenarios)}] {sc_id} — starting "
                f"({i-1} done, {len(scenarios)-i+1} remaining)"
            )

            output_dir = batch_dir / sc_id

            try:
                record = process_scenario_full(scenario, output_dir, config)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[batch_full]   {sc_id}: UNEXPECTED CRASH: {e}")
                record = {
                    "scenario": scenario,
                    "final_status": "failed",
                    "error_message": f"unhandled exception: {e}",
                    "error_stage": "unknown",
                    "experiment": EXPERIMENT_NAME,
                }

            records.append(record)

            elapsed = time.time() - scenario_started
            picker = record.get("orientation_picker") or {}
            orient = picker.get("orientation", "—")
            status = record.get("final_status", "?")
            stage_note = (
                f" (failed at: {record.get('error_stage', '?')})"
                if status != "success" else ""
            )
            print(
                f"[batch_full]   {sc_id}: {status.upper()} in {elapsed:.1f}s "
                f"(orientation: {orient}){stage_note}"
            )

            # Periodic refresh every 3 scenarios — full pipeline takes longer
            # per scenario, so checkpoint more often
            if i % 3 == 0:
                _write_manifest_and_overview(
                    batch_dir, records, started_at, interrupted=False
                )
                print(f"[batch_full]   (overview.html refreshed at {i}/{len(scenarios)})")

    except KeyboardInterrupt:
        interrupted = True
        print("")
        print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("[batch_full] interrupted by user (Ctrl+C)")
        print(f"[batch_full] writing partial overview for {len(records)} completed scenarios...")
        print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Final overview write
    _write_manifest_and_overview(batch_dir, records, started_at, interrupted=interrupted)

    succeeded = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - succeeded
    elapsed_total = time.time() - started_at

    orient_counts: dict[str, int] = {}
    failure_stages: dict[str, int] = {}
    for r in records:
        o = (r.get("orientation_picker") or {}).get("orientation", "—")
        orient_counts[o] = orient_counts.get(o, 0) + 1
        if r.get("final_status") != "success":
            stage = r.get("error_stage", "unknown")
            failure_stages[stage] = failure_stages.get(stage, 0) + 1

    print("")
    print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"[batch_full] DONE{'  (interrupted)' if interrupted else ''}")
    print(f"[batch_full]   succeeded:     {succeeded} / {len(records)}")
    print(f"[batch_full]   failed:        {failed}")
    print(f"[batch_full]   wall time:     {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")
    print(f"[batch_full]   orientations:  " + ", ".join(
        f"{k}={v}" for k, v in sorted(orient_counts.items())
    ))
    if failure_stages:
        print(f"[batch_full]   failures by stage:  " + ", ".join(
            f"{k}={v}" for k, v in sorted(failure_stages.items())
        ))
    print(f"[batch_full]   overview.html: {batch_dir / 'overview.html'}")
    print(f"[batch_full]   manifest.json: {batch_dir / 'batch_manifest.json'}")
    print("[batch_full] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return 0 if (failed == 0 and not interrupted) else 2


if __name__ == "__main__":
    sys.exit(main())