"""
prompt_builder_qwen.py — Qwen-tuned Step 2 prompt generation via Opus 4.7.

Self-contained module for the qwen_tuned_prompt experiment. Mirrors the shape
of the project's main src/prompt_builder.py but:
  - Uses the new master_prompt_step2_qwen.md as the system prompt
  - Updates the user-message TASK section to align with Qwen tuning:
      * Use "the person from the first image" / "the product from the second image"
      * Include the product orientation lock clause
      * Include the anatomy sanity clause
      * Word budget 280-380
  - Does NOT modify the original src/prompt_builder.py — that one remains
    unchanged for the existing Plan A pipeline.

Reads static context (persona.yaml, brand.yaml, do_dont.md, product.yaml) from
the project root the same way the original builder does. Caches them per process.

Usage from inside this experiment:
    from experiments.step2_qwen_edit_2511.qwen_tuned_prompt.prompt_builder_qwen import (
        build_step_2_prompt_qwen,
    )
    output = build_step_2_prompt_qwen(scenario, step_1_output)
"""

import os
import re
import json
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = "claude-opus-4-7"

# This experiment's master prompt (sibling of project-root prompts/master_prompt_step2.md)
EXPERIMENT_DIR = Path(__file__).resolve().parent
QWEN_SYSTEM_PROMPT_PATH = EXPERIMENT_DIR / "master_prompt_step2_qwen.md"

# Static context paths — relative to project root (same as the original builder)
PERSONA_YAML_PATH = Path("assets/persona.yaml")
PRODUCT_YAML_PATH = Path("assets/product.yaml")
BRAND_YAML_PATH = Path("brand/brand.yaml")
DO_DONT_MD_PATH = Path("brand/do_dont.md")

_client: Anthropic | None = None
_static_context_cache: dict[str, str] | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
        _client = Anthropic(api_key=api_key)
    return _client


def _load_static_context() -> dict[str, str]:
    """Load and cache the four static context files."""
    global _static_context_cache
    if _static_context_cache is not None:
        return _static_context_cache

    paths = {
        "persona_yaml": PERSONA_YAML_PATH,
        "product_yaml": PRODUCT_YAML_PATH,
        "brand_yaml": BRAND_YAML_PATH,
        "do_dont_md": DO_DONT_MD_PATH,
    }
    missing = [(k, p) for k, p in paths.items() if not p.exists()]
    if missing:
        msg = "Missing required context files (run from project root):\n" + "\n".join(
            f"  - {k}: {p}" for k, p in missing
        )
        raise FileNotFoundError(msg)

    _static_context_cache = {k: p.read_text(encoding="utf-8") for k, p in paths.items()}
    return _static_context_cache


def _parse_json(text: str) -> dict:
    """Strip code fences and parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def build_step_2_prompt_qwen(scenario: dict, step_1_output: dict) -> dict:
    """
    Build the Qwen-tuned Step 2 prompt envelope.

    Receives both the original scenario AND the Step 1 output (which has the
    product_slot bridge data and the lighting language to echo). Calls Opus 4.7
    with the Qwen-tuned master prompt and returns the parsed JSON envelope.

    Args:
        scenario: parsed scenarios.yaml entry for this scenario
        step_1_output: parsed 02_step1_prompt.json from the baseline Plan A run

    Returns:
        dict with keys: step_2_image_prompt (str), word_count (int),
        structure_breakdown, fal_qwen_params, image_inputs_required,
        compliance_check.
    """
    if not QWEN_SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"missing system prompt: {QWEN_SYSTEM_PROMPT_PATH}")

    system_prompt = QWEN_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    ctx = _load_static_context()

    user_message = "\n".join(
        [
            "=== product.yaml (INTERNAL VALIDATION ONLY — never describe in prompt) ===",
            ctx["product_yaml"],
            "",
            "=== do_dont.md (compliance) ===",
            ctx["do_dont_md"],
            "",
            "=== ORIGINAL SCENARIO ===",
            json.dumps(scenario, indent=2),
            "",
            "=== STEP 1 OUTPUT (use product_slot for placement, lighting from sentence 4) ===",
            json.dumps(step_1_output, indent=2),
            "",
            "=== TASK ===",
            "Build the Qwen-tuned Step 2 prompt envelope.",
            "",
            "BREVITY IS REQUIRED. Past Qwen runs with 500+ word prompts performed WORSE",
            "  than 380-word versions of the same prompt. Stay between 320 and 410 words.",
            "  HARD CEILING is 430 words. Do NOT exceed it. If a clause is redundant with",
            "  another, drop it. If two clauses say the same thing, keep the shorter one.",
            "  Match the calibration examples' length (~387 words each). Do not be more",
            "  verbose than the examples — they were tuned for Qwen's signal-to-noise",
            "  characteristics.",
            "",
            "Use 'the person from the first image' / 'the product from the second image' /",
            "  'the first image' / 'the second image' positional reference syntax",
            "  (REQUIRED in this Qwen variant — do NOT use generic 'reference photo' language).",
            "Thread 'keep X unchanged' anchors through Sentence 1 (keep her face unchanged,",
            "  keep her hair unchanged, keep her outfit unchanged, keep the scene unchanged).",
            "Echo Step 1's lighting language from sentence 4 verbatim in Sentence 4.",
            "Sentence 2 MUST include the rigid-rotation orientation clause:",
            "  'The packaging is a rigid object — its proportions and printed design match",
            "   the second image exactly. The box can be rotated naturally for the holding",
            "   pose, but the printed design rotates with it as one coherent surface; never",
            "   reflow, redesign, or rearrange the layout to fit a different orientation;",
            "   never mirror or reverse the text.'",
            "  This REPLACES the older 'natural landscape orientation, do not rotate to",
            "  vertical' language. Rotation IS allowed; redesign/reflow IS NOT.",
            "Sentence 2 MUST include positive + negative position re-anchoring",
            "  (e.g. 'at chest level, not above her head, not at her hip').",
            "Sentence 3 MUST include the anatomy sanity clause with occlusion handling",
            "  (exactly two arms, two hands, TWO LEGS, five fingers per hand;",
            "   fingers and hands occluded by the product or her body still fully exist —",
            "   do not omit them because they are hidden; no extra limbs, no extra digits,",
            "   no fused or warped fingers).",
            "Sentence 4 MUST include the single product clause at its start",
            "  ('exactly ONE physical Alluvi product is visible — never two copies, never",
            "   duplicates'; for mirror-reflection scenarios add 'the mirror reflection",
            "   counts as the same product').",
            "Include the white base preservation clause in Sentence 4.",
            "",
            "Word count for step_2_image_prompt: 320-410 (HARD CEILING 430).",
        ]
    )

    print(f"[prompt_builder_qwen] Step 2 (Qwen-tuned) -> Opus 4.7 for scenario {scenario['id']}")
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    output = _parse_json(response.content[0].text)

    wc = output.get("word_count", 0)
    print(f"[prompt_builder_qwen]   Step 2 done: word_count={wc}")
    return output